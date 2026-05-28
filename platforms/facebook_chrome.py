"""
Facebook Reels uploader for FrameWise Cinema Page — via attached Chrome.

Architecture (same as platforms/rumble_chrome.py):
  - Connects to the persistent Chrome instance running on port 9222
    (launched by ensure_chrome.sh, profile at ~/Library/Application Support/FrameWiseChrome)
  - User must be logged into FB in that Chrome (cookies persist across runs)
  - Uses Chrome DevTools Protocol (CDP) Input.dispatchMouseEvent to fire
    real-browser-level mouse events — FB's React UI accepts these as real clicks
    where synthetic Selenium clicks fail

PUBLISH FLOW (4 stages discovered via reverse engineering):
  Stage 1: Page profile → click 'Reel' button → modal opens
  Stage 2: Drop file → 'Next' (advances to Edit Reel step)
  Stage 3: 'Next' (advances from Edit Reel → audience/scheduling step)
  Stage 4: 'Post' button publishes the Reel
"""

import json, logging, subprocess, time
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

DEBUG_PORT = 9222
PAGE_ID_DEFAULT = "61590613942018"  # FrameWise Cinema FB Page ID


def _attach_chrome():
    """Attach Selenium to running Chrome via remote-debugging-port."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    import urllib.request

    # Verify port is alive
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=3).read()
    except Exception as e:
        raise RuntimeError(f"Chrome not reachable on port {DEBUG_PORT}. Run ensure_chrome.sh first. {e}")

    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{DEBUG_PORT}")
    return webdriver.Chrome(options=opts)


def _ensure_fb_tab(driver):
    """Force a VIRGIN Facebook tab: close ALL existing fb.com tabs + open ONE fresh.
    Prevents stale-state failures from re-using a tab whose previous upload half-completed."""
    PAGE_URL = "https://www.facebook.com/profile.php?id=61590613942018"

    # Close every existing facebook.com tab (they may have stale composer state)
    to_close = []
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if "facebook.com" in driver.current_url:
                to_close.append(h)
        except Exception:
            continue
    for h in to_close:
        try:
            driver.switch_to.window(h)
            driver.close()
        except Exception:
            pass

    # Open a fresh FB tab via Chrome debug API (PUT)
    import urllib.request
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{DEBUG_PORT}/json/new?{PAGE_URL}",
            method='PUT',
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        # Fall back: open via JS in remaining window
        try:
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
                driver.execute_script(f"window.open('{PAGE_URL}', '_blank');")
        except Exception:
            pass

    # Poll up to 20s for the fresh FB tab to appear + load
    for _ in range(20):
        time.sleep(1)
        for h in driver.window_handles:
            try:
                driver.switch_to.window(h)
                if "facebook.com" in driver.current_url:
                    return True
            except Exception:
                continue
    return False


def upload(video_path: Path, title: str, description: str, tags: List[str], cfg: dict) -> str:
    """Post a Reel to FrameWise Cinema page. Returns the public Reel URL.

    Args:
        video_path: local path to the rendered .mp4
        title:       short title (not used by FB Reels — kept for API symmetry with YT/Rumble)
        description: caption text (will be posted to the Reel; FB strips/trims as needed)
        tags:        list of hashtags (currently bundled into description by upstream caller)
        cfg:         credentials.json contents (provides facebook_page_id if set)

    Returns the public Reel URL on success; raises RuntimeError on failure."""
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    page_id = cfg.get("facebook_page_id", PAGE_ID_DEFAULT)
    page_url = f"https://www.facebook.com/profile.php?id={page_id}"

    # NOTE: do NOT activate Chrome. CDP Input.* events work without foreground focus,
    # so the user can keep working in their current app while this runs.
    d = _attach_chrome()
    if not _ensure_fb_tab(d):
        raise RuntimeError("could not switch to a facebook.com tab")

    # ============================================================
    # DUPLICATE PREVENTION:
    # Snapshot the Reels tab BEFORE attempting upload. If a NEW reel
    # appears after publish, that's our success URL — even if our
    # script's intermediate detection said "fail" and would have retried.
    # This stops the "retry posts duplicates" problem.
    # ============================================================
    def _snapshot_reel_ids():
        """Return the set of reel IDs currently on the Page's Reels tab."""
        try:
            d.get(f"https://www.facebook.com/profile.php?id={page_id}&sk=reels_tab")
            time.sleep(6)
            ids = d.execute_script("""
            var out = new Set();
            document.querySelectorAll('a[href*="/reel/"]').forEach(function(el){
                var m = (el.href||'').match(/\\/reel\\/(\\d+)/);
                if(m) out.add(m[1]);
            });
            return Array.from(out);
            """)
            return set(ids or [])
        except Exception as e:
            log.warning(f"FB: snapshot failed: {e}")
            return set()

    log.info("FB: snapshotting existing reels before upload (duplicate-prevention)")
    pre_ids = _snapshot_reel_ids()
    log.info(f"FB: {len(pre_ids)} reels already on Page before this upload")

    # ---- helpers wired to driver ----

    def cdp_click(elem_id):
        """Fire a real Chrome mouse-click at the element's viewport center.
        Returns False if element is missing or off the viewport."""
        rect = d.execute_script("""
        var el = document.getElementById(arguments[0]);
        if(!el) return null;
        var r = el.getBoundingClientRect();
        return {x: r.left + r.width/2, y: r.top + r.height/2};
        """, elem_id)
        if not rect:
            return False
        vp = d.execute_script("return {w: window.innerWidth, h: window.innerHeight};")
        if rect['x'] < 0 or rect['y'] < 0 or rect['x'] > vp['w'] or rect['y'] > vp['h']:
            log.warning(f"FB: element {elem_id} off-viewport ({rect['x']:.0f},{rect['y']:.0f})")
            return False
        for ev in ('mouseMoved', 'mousePressed', 'mouseReleased'):
            d.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': ev, 'x': rect['x'], 'y': rect['y'],
                'button': 'left' if ev != 'mouseMoved' else 'none',
                'clickCount': 1 if ev != 'mouseMoved' else 0,
            })
        return True

    def find_visible_button(text_match):
        """Find a button by exact text whose center is on the viewport."""
        return d.execute_script("""
        var match = arguments[0].toLowerCase();
        var vw = window.innerWidth, vh = window.innerHeight;
        var found = null;
        document.querySelectorAll('div[role=button], button').forEach(function(el){
            if(found || el.offsetParent === null) return;
            var t = (el.textContent||'').trim().toLowerCase();
            if(t !== match || el.getAttribute('aria-disabled') === 'true') return;
            var r = el.getBoundingClientRect();
            var cx = r.left + r.width/2, cy = r.top + r.height/2;
            if(cx < 0 || cy < 0 || cx > vw || cy > vh) return;
            if(!el.id) el.id = 'btn_'+Math.random().toString(36).substring(7);
            found = el.id;
        });
        return found;
        """, text_match)

    # ---- Stage 1: navigate to Page + click Reel ----
    log.info("FB: navigating to Page profile")
    d.get(page_url)
    time.sleep(8)

    log.info("FB: clicking 'Reel' button")
    # The 'Reel' button often sits below the viewport when the page first loads
    # (especially with a narrow Chrome window). Find it, scroll it into the
    # center of the viewport, then click via CDP.
    reel_id = d.execute_script("""
    var found = null;
    document.querySelectorAll('div').forEach(function(el){
        if(found || el.offsetParent === null) return;
        if(el.getAttribute('aria-label') === 'Reel'){
            if(!el.id) el.id = 'fb_reel_btn';
            found = el.id;
        }
    });
    return found;
    """)
    if not reel_id:
        # Sometimes FB renders Reel as a button instead of a div; or it's still loading
        d.execute_script("window.scrollTo(0, 400);")
        time.sleep(2)
        reel_id = d.execute_script("""
        var found = null;
        document.querySelectorAll('[aria-label="Reel"], [aria-label="Reels"]').forEach(function(el){
            if(found || el.offsetParent === null) return;
            if(!el.id) el.id = 'fb_reel_btn';
            found = el.id;
        });
        return found;
        """)
    if not reel_id:
        raise RuntimeError("FB: 'Reel' button not found on Page profile")

    # Scroll the Reel button into center of viewport so cdp_click's viewport check passes
    d.execute_script("""
    var el = document.getElementById(arguments[0]);
    if (el) el.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
    """, reel_id)
    time.sleep(1.5)

    if not cdp_click(reel_id):
        # Retry once after scrolling up to the top (different Chrome window heights need different positioning)
        d.execute_script("window.scrollTo(0, 0); document.getElementById(arguments[0]).scrollIntoView({block: 'center'});", reel_id)
        time.sleep(1.5)
        if not cdp_click(reel_id):
            raise RuntimeError("FB: failed to click 'Reel' button (still off-viewport after scroll)")
    time.sleep(5)

    # ---- Stage 2: send video file ----
    log.info(f"FB: sending video {video_path.name}")
    fid = d.execute_script("""
    var found = null;
    document.querySelectorAll('input[type=file]').forEach(function(el){
        if(found) return;
        if((el.getAttribute('accept')||'').indexOf('video') !== -1){
            if(!el.id) el.id = 'fb_file_in';
            found = el.id;
        }
    });
    return found;
    """)
    if not fid:
        raise RuntimeError("FB: video file input not found after opening Reel composer")
    from selenium.webdriver.common.by import By
    d.find_element(By.ID, fid).send_keys(str(video_path.resolve()))
    log.info("FB: waiting 30s for upload to process")
    time.sleep(30)

    # ---- Stage 2.5: advance to Edit Reel step, then fill caption ----
    # The caption (contenteditable div) lives on the Edit Reel step which appears
    # after the FIRST Next click. We use CDP Input.insertText to type the caption
    # without requiring Chrome to be in the foreground (no osascript keystrokes).

    # First Next: upload step → Edit Reel step
    log.info("FB: clicking Next to advance to Edit Reel step")
    for retry in range(3):
        nid = find_visible_button('next')
        if nid and cdp_click(nid):
            break
        time.sleep(2)
    time.sleep(5)

    # Find caption field on the Edit Reel step.
    # FB renders TWO contenteditables in the dialog — one at x=-212 (off-viewport,
    # hidden sub-panel) and one at x=277 (the actual visible caption). Layout varies
    # between runs. ALWAYS pick the IN-VIEWPORT one with w>=100 and h>=15.
    log.info("FB: locating caption field (in-viewport contenteditable)")
    cap_id = None
    for retry in range(15):
        all_caps = d.execute_script("""
        var out = [];
        document.querySelectorAll('div[role=dialog] div[contenteditable=true]').forEach(function(el){
            if(el.offsetParent === null) return;
            var r = el.getBoundingClientRect();
            var cx = r.left + r.width/2, cy = r.top + r.height/2;
            var in_vp = (cx >= 0 && cy >= 0 && cx <= window.innerWidth && cy <= window.innerHeight);
            if(!el.id) el.id = 'fb_cap_'+Math.random().toString(36).substring(7);
            out.push({id: el.id, w: Math.round(r.width), h: Math.round(r.height), in_viewport: in_vp});
        });
        return out;
        """)
        # Prefer in-viewport contenteditable with reasonable size
        chosen = next((c for c in all_caps
                       if c['in_viewport'] and c['w'] >= 100 and c['h'] >= 15), None)
        if chosen:
            cap_id = chosen['id']
            log.info(f"FB: caption field found on attempt {retry+1}: {chosen}")
            break
        time.sleep(1)

    if cap_id:
        # Build caption text: description + hashtags
        full_caption = description.strip()
        if tags:
            tag_str = " ".join("#" + t.strip().replace(" ", "").replace(",", "")
                               for t in tags if t.strip())
            if tag_str and "#" not in full_caption:
                full_caption = full_caption + " " + tag_str

        # FB's Reel caption uses Lexical editor (data-lexical-editor="true") which
        # ONLY accepts trusted keyboard events. Synthetic events (insertText,
        # execCommand, dispatched InputEvent) get rejected by Lexical's state machine.
        # The ONE reliable way is paste from clipboard via Cmd+V — that's a real OS
        # clipboard event Lexical accepts.
        log.info(f"FB: caption ({len(full_caption)} chars) → clipboard → Cmd+V paste")

        # Put the caption text in macOS clipboard via pbcopy
        subprocess.run(['pbcopy'], input=full_caption.encode(), check=True)

        # Activate Chrome briefly so Cmd+V routes to it
        subprocess.run(['osascript', '-e',
                        'tell application "Google Chrome" to activate'],
                       capture_output=True)
        time.sleep(1.5)

        # Click into the caption field at OS level (CDP click to focus + position cursor)
        cdp_click(cap_id)
        time.sleep(0.8)
        d.execute_script("document.getElementById(arguments[0]).focus();", cap_id)
        time.sleep(0.3)

        # Cmd+V via System Events — fires a TRUSTED paste event Lexical respects
        subprocess.run(['osascript', '-e',
                        'tell application "System Events" to keystroke "v" using {command down}'],
                       capture_output=True)
        time.sleep(3)

        # Verify caption landed
        landed = d.execute_script("""
        var el = document.getElementById(arguments[0]);
        return el ? el.textContent.trim().substring(0,80) : '';
        """, cap_id)
        log.info(f"FB: caption field now contains: {landed[:80]!r}")
    else:
        log.warning("FB: caption field not found after 15 retries — posting without caption")

    # ---- Stage 3-5: navigate remaining wizard to Publish ----
    posted = False
    prev_state = None
    for step in range(12):
        # Detect terminal state
        in_dialog = d.execute_script("return !!document.querySelector('div[role=dialog]');")
        if not in_dialog:
            log.info(f"FB: dialog closed after step {step} — assuming post sent")
            posted = True
            break

        # Try Post / Publish / Share Now first
        terminal_btn = None
        for label in ('post', 'publish', 'share now', 'share'):
            bid = find_visible_button(label)
            if bid:
                terminal_btn = (label, bid)
                break

        if terminal_btn:
            label, bid = terminal_btn
            log.info(f"FB: clicking terminal button {label!r}")
            if cdp_click(bid):
                time.sleep(10)
                # Detect post-completion: dialog closes or success indicator
                if not d.execute_script("return !!document.querySelector('div[role=dialog]');"):
                    posted = True
                    break
                # else continue — there may be follow-up upsell dialogs
                continue

        # Otherwise click Next (visible only — filters out the offscreen duplicate)
        nid = find_visible_button('next')
        if not nid:
            log.warning("FB: no visible Next or Publish button — wizard stuck")
            break
        if not cdp_click(nid):
            log.warning("FB: Next click failed")
            break
        time.sleep(5)

        # State-change watchdog (avoid infinite Next loop on same step)
        snapshot = d.execute_script("""
        var btns = [];
        document.querySelectorAll('div[role=dialog] div[role=button], div[role=dialog] button').forEach(function(el){
            if(el.offsetParent !== null){
                var t = (el.textContent||'').trim().substring(0,30);
                if(t) btns.push(t);
            }
        });
        return btns.sort().join('|');
        """)
        if snapshot == prev_state:
            log.warning("FB: state unchanged across cycles — bailing wizard loop")
            break
        prev_state = snapshot

    # ============================================================
    # DUPLICATE-AWARE VERIFICATION (replaces the old `if not posted: raise`):
    # FB sometimes "silently posts" — our wizard detection said fail, but
    # the Reel actually went up. Check the Reels tab and diff against the
    # pre-snapshot. If a NEW reel ID appeared, that's our success.
    # If not, it's a real failure.
    # ============================================================
    log.info("FB: post-upload check — looking for NEW reel ID vs pre-snapshot")
    time.sleep(8)  # let FB index the new post
    post_ids = _snapshot_reel_ids()
    new_ids = post_ids - pre_ids
    log.info(f"FB: pre={len(pre_ids)} ids, post={len(post_ids)} ids, NEW={len(new_ids)}")

    if not new_ids:
        # No new reel — the upload truly failed
        raise RuntimeError(
            f"FB: no new reel appeared on Reels tab (pre={len(pre_ids)}, post={len(post_ids)}) "
            f"— upload truly failed, NOT retrying to avoid duplicates"
        )

    if len(new_ids) > 1:
        log.warning(f"FB: multiple new reels detected ({new_ids}) — taking the first; "
                    f"manual cleanup may be needed")

    new_id = sorted(new_ids)[0]
    reel_url = f"https://www.facebook.com/reel/{new_id}/"
    log.info(f"FB ✅  {reel_url}  (id={new_id})")
    return reel_url


if __name__ == "__main__":
    import argparse, sys, json as _json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--upload", required=True, help="path to video")
    p.add_argument("--description", default="Test caption for FrameWise Cinema #Shorts")
    args = p.parse_args()
    cfg_path = Path.home() / "FrameWise-Cinema/config/credentials.json"
    cfg = _json.loads(cfg_path.read_text())
    url = upload(Path(args.upload), title="", description=args.description, tags=[], cfg=cfg)
    print(f"\nDONE: {url}")
