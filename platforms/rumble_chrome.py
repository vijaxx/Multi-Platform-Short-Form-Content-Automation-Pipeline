"""
Rumble uploader — production version using attached real Chrome.

WHY: Rumble's Cloudflare bot detection and React form widgets defeat both
vanilla Selenium and undetected-chromedriver. The bulletproof workaround is
to drive a REAL Chrome instance that was launched normally (no automation
flags) and attach Selenium to it via the DevTools remote-debugging-port.

ONE-TIME SETUP (run by ensure_chrome.sh — see below):
  1. Launch Chrome with:
       --user-data-dir=$HOME/Library/Application\ Support/FrameWiseChrome
       --remote-debugging-port=9222
       --no-first-run --no-default-browser-check
  2. User manually logs into rumble.com once. Cookies persist in the profile.

DAILY USE:
  upload(video_path, title, description, tags, cfg) — attaches to the running
  Chrome on port 9222 and drives the upload form to completion.
"""

import json, logging, time
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

DEBUG_PORT = 9222
PROFILE_DIR = Path.home() / "Library/Application Support/FrameWiseChrome"
UPLOAD_URL = "https://rumble.com/upload.php"

# Maps category names to Rumble's internal data-value IDs
CATEGORY_VALUES = {
    "Automotive": "9",
    "Cooking": "2",
    "Entertainment": "15",
    "Finance & Crypto": "16",
    "Gaming": "4",
    "Health & Science": "6",
    "HowTo": "10",
    "Music": "12",
    "News": "9",
    "Podcasts": "20",
    "Sports": "5",
    "Technology": "8",
    "Travel": "13",
    "Viral": "23",
    "Vlogs": "21",
}


def _attach_chrome():
    """Attach Selenium to the running Chrome via the remote debugging port.
    Returns the WebDriver. Raises RuntimeError if Chrome isn't reachable."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        raise SystemExit("Run: pip3 install selenium")

    # Verify the debug endpoint is alive before opening a driver session
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=3).read()
    except Exception as e:
        raise RuntimeError(
            f"Chrome not reachable on port {DEBUG_PORT}. "
            f"Run ensure_chrome.sh first. Error: {e}"
        )

    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{DEBUG_PORT}")
    return webdriver.Chrome(options=opts)


def _switch_to_upload_tab(driver):
    """Find/create the upload.php tab and switch to it."""
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "upload.php" in driver.current_url:
            return True
    # No upload tab — open one in the first window
    driver.switch_to.window(driver.window_handles[0])
    driver.execute_script(f"window.open('{UPLOAD_URL}', '_blank');")
    time.sleep(2)
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "upload.php" in driver.current_url:
            return True
    return False


def _fresh_upload_tab(driver):
    """Force a VIRGIN upload tab: close all existing rumble tabs + open ONE fresh.
    Use this before every upload attempt — prevents stale-state failures from
    re-using a tab whose previous upload half-completed."""
    # Close every existing rumble.com tab
    to_close = []
    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            if "rumble.com" in driver.current_url:
                to_close.append(handle)
        except Exception:
            continue
    for handle in to_close:
        try:
            driver.switch_to.window(handle)
            driver.close()
        except Exception:
            pass
    # Need at least one window to remain; if we closed everything, open a fresh tab
    if not driver.window_handles:
        # No tabs left — open via Chrome's debug API (PUT new tab)
        import urllib.request
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{DEBUG_PORT}/json/new?{UPLOAD_URL}", method='PUT'
            )
            urllib.request.urlopen(req, timeout=5).read()
            time.sleep(2)
        except Exception:
            pass
    # Switch to first remaining window and navigate to fresh upload page
    if driver.window_handles:
        driver.switch_to.window(driver.window_handles[0])
        # Open new tab via JS, then switch to it
        driver.execute_script(f"window.open('{UPLOAD_URL}', '_blank');")
        time.sleep(2)
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if "rumble.com/upload" in driver.current_url:
                return True
    return False


def upload(video_path: Path, title: str, description: str, tags: List[str],
           cfg: dict, category: str = "Entertainment") -> str:
    """Upload a video to Rumble. Returns the published video URL.

    Requires Chrome to be running with --remote-debugging-port=9222 and
    user already logged into Rumble. Use ensure_chrome.sh to launch."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    d = _attach_chrome()

    try:
        # Use a FRESH upload tab every attempt (avoids stale state from previous fails)
        _fresh_upload_tab(d)
        time.sleep(6)
        # Belt: hard navigate to upload page in the new tab
        d.get(UPLOAD_URL)
        time.sleep(4)

        if "auth.rumble.com" in d.current_url or "login" in d.current_url:
            raise RuntimeError(
                "Chrome session not logged into Rumble. "
                "Open chrome on port 9222 and sign in manually first."
            )

        # 1. Send the video file
        log.info(f"Rumble: uploading file {video_path.name}")
        file_input = d.find_element(By.ID, "Filedata")
        file_input.send_keys(str(video_path.resolve()))
        time.sleep(3)

        # 2. Fill title/description/tags
        log.info("Rumble: filling metadata")
        # Strip non-BMP characters (emojis above U+FFFF) — ChromeDriver send_keys
        # crashes on them with "ChromeDriver only supports characters in the BMP"
        def _bmp_safe(s):
            return ''.join(ch for ch in s if ord(ch) < 0x10000)

        for field_id, value in [
            ("title", _bmp_safe(title)[:100]),
            ("description", _bmp_safe(description)[:2000]),
            ("tags", _bmp_safe(", ".join(tags[:10]) if isinstance(tags, list) else str(tags))),
        ]:
            el = d.find_element(By.ID, field_id)
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            el.clear()
            el.send_keys(value)

        # 3. Open category dropdown + click chosen option
        # AGGRESSIVE FIX (May 2026): the dropdown is fragile. Strategy:
        #   - Use CDP click (more trusted than Selenium native)
        #   - Verify the .select-options-container actually opens before polling for option
        #   - If not open after 3s, re-click up to 3 times
        #   - Once open, poll up to 60s for the option (Rumble's React lazy-renders the list)
        log.info(f"Rumble: selecting category={category!r}")

        def _find_primary_input():
            for s in d.find_elements(By.CSS_SELECTOR, "input.select-search-input"):
                if "primary" in (s.get_attribute("data-default-placeholder") or "").lower():
                    return s
            return None

        def _cdp_click_element(elem):
            """CDP-level mouse click on a Selenium WebElement at its viewport center."""
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
            time.sleep(0.3)
            rect = d.execute_script("""
                var r = arguments[0].getBoundingClientRect();
                return {x: r.left + r.width/2, y: r.top + r.height/2};
            """, elem)
            for ev in ('mouseMoved', 'mousePressed', 'mouseReleased'):
                d.execute_cdp_cmd('Input.dispatchMouseEvent', {
                    'type': ev, 'x': rect['x'], 'y': rect['y'],
                    'button': 'left' if ev != 'mouseMoved' else 'none',
                    'clickCount': 1 if ev != 'mouseMoved' else 0,
                })

        def _dropdown_is_open():
            """Returns True if the options container is visible AND has options."""
            return d.execute_script("""
                var any = false;
                document.querySelectorAll('.select-options-container').forEach(function(el){
                    if(el.offsetParent !== null && el.querySelectorAll('.select-option').length > 0){
                        any = true;
                    }
                });
                return any;
            """)

        primary_input = _find_primary_input()
        if primary_input is None:
            raise RuntimeError("primary category dropdown input not found")

        # Try up to 3 times to OPEN the dropdown
        dropdown_open = False
        for open_attempt in range(3):
            _cdp_click_element(primary_input)
            time.sleep(3)
            if _dropdown_is_open():
                log.info(f"Rumble: dropdown opened on attempt {open_attempt+1}")
                dropdown_open = True
                break
            log.warning(f"Rumble: dropdown didn't open (attempt {open_attempt+1}/3)")
            time.sleep(2)

        if not dropdown_open:
            raise RuntimeError("Rumble: category dropdown failed to open after 3 clicks")

        # Dropdown IS open — poll up to 60s for our specific option to render
        target = None
        for poll in range(60):
            target = d.execute_script("""
                var label = arguments[0];
                var found = null;
                document.querySelectorAll('.select-option').forEach(function(el){
                    if(found) return;
                    if(el.textContent.trim() === label && el.offsetParent !== null){
                        found = el;
                    }
                });
                return found;
            """, category)
            if target is not None:
                log.info(f"Rumble: {category!r} option appeared at +{poll}s")
                break
            time.sleep(1)
        if target is None:
            raise RuntimeError(f"category option {category!r} not in opened dropdown after 60s")

        d.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
        time.sleep(0.3)
        ActionChains(d).move_to_element(target).pause(0.2).click().perform()
        time.sleep(1)

        # 4. Tick ALL visible unchecked checkboxes (rights, terms, syndication options)
        log.info("Rumble: ticking all visible checkboxes")
        d.execute_script("""
            document.querySelectorAll('input[type=checkbox]').forEach(function(b){
                if(b.offsetParent !== null && !b.checked){
                    b.click();
                }
            });
        """)
        time.sleep(0.5)

        # 5. Click step 1 → step 2 (#submitForm)
        log.info("Rumble: clicking submitForm (step 1)")
        d.execute_script("""
            var el = document.getElementById('submitForm');
            el.scrollIntoView({block:'center'});
            el.click();
            var $$ = window.jQuery || window.$;
            if($$) $$('#submitForm').trigger('click');
        """)

        # Wait for step 2 (submitForm2 becomes visible)
        log.info("Rumble: waiting for step 2...")
        for _ in range(120):
            time.sleep(1)
            visible = d.execute_script("""
                var sf2 = document.getElementById('submitForm2');
                return sf2 && sf2.offsetParent !== null;
            """)
            if visible:
                break
        else:
            raise RuntimeError("step 2 never appeared after submitForm click")

        # 6. Click step 2 license: "Rumble Only (non-exclusive)" — crcval=6.
        # As of late May 2026 Rumble added a license-selection gate. Without picking one,
        # submitForm2 silently doesn't advance. Click .greenLink[crcval=6] = Rumble Only.
        log.info("Rumble: selecting 'Rumble Only (non-exclusive)' license on step 2")
        time.sleep(1)
        d.execute_script("""
            var clicked = false;
            document.querySelectorAll('a.greenLink').forEach(function(el){
                if(clicked) return;
                if((el.getAttribute('crcval')||'') === '6'){
                    el.scrollIntoView({block:'center'});
                    el.click();
                    clicked = true;
                }
            });
        """)
        time.sleep(2)

        # Also tick any step-2 checkboxes that might be required (e.g. terms of service)
        d.execute_script("""
            document.querySelectorAll('input[type=checkbox]').forEach(function(b){
                if(b.offsetParent !== null && !b.checked){ b.click(); }
            });
        """)
        time.sleep(1)

        # 7. Click step 2 final submit (#submitForm2)
        log.info("Rumble: clicking submitForm2 (final publish)")
        d.execute_script("""
            var el = document.getElementById('submitForm2');
            el.scrollIntoView({block:'center'});
            el.click();
            var $$ = window.jQuery || window.$;
            if($$) $$('#submitForm2').trigger('click');
        """)

        # 7. Wait for "VIDEO UPLOAD COMPLETE!" + extract REAL video URL
        # IMPORTANT: the success page also shows "related video" recommendations whose hrefs
        # match rumble.com/vXXX — must distinguish our video from those:
        #   Strategy A: <a> whose text starts with "View" — that's the just-uploaded video link
        #   Strategy B: <textarea id="direct"> holds the canonical Direct Link URL
        log.info("Rumble: waiting for upload-complete page...")
        video_url = None
        for _ in range(240):
            time.sleep(1)
            video_url = d.execute_script("""
                var found = null;
                document.querySelectorAll('a[href*="rumble.com/v"]').forEach(function(el){
                    if(found) return;
                    var t = (el.textContent||'').trim();
                    if(t.indexOf('View') === 0 && el.offsetParent !== null){
                        found = el.href;
                    }
                });
                return found;
            """)
            if video_url:
                break
            # Strategy B: pull the canonical URL from Rumble's "Direct Link" textarea
            direct = d.execute_script("""
                var t = document.getElementById('direct');
                return t ? (t.value || t.textContent || '').trim() : null;
            """)
            if direct and direct.startswith("http"):
                video_url = direct
                break

        if not video_url:
            raise RuntimeError("upload completed but no video URL found on page")

        log.info(f"Rumble ✅  {video_url}")

        # Refresh saved cookies for next run
        try:
            cookie_path = Path.home() / "FrameWise-Cinema/config/rumble_cookies.json"
            cookie_path.write_text(json.dumps(d.get_cookies(), indent=2))
        except Exception:
            pass

        return video_url

    finally:
        # IMPORTANT: do NOT quit the driver — that would kill the user's Chrome.
        # Just disconnect.
        pass


if __name__ == "__main__":
    import argparse, sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--upload", required=True, help="path to video")
    p.add_argument("--title", default="FrameWise Cinema test")
    p.add_argument("--description", default="Test upload via attached Chrome.")
    p.add_argument("--tags", default="motivation,quotes")
    p.add_argument("--category", default="Entertainment")
    args = p.parse_args()
    cfg_path = Path.home() / "FrameWise-Cinema/config/credentials.json"
    cfg = json.loads(cfg_path.read_text())
    url = upload(
        Path(args.upload), args.title, args.description,
        args.tags.split(","), cfg, args.category,
    )
    print(f"\nDONE: {url}")
