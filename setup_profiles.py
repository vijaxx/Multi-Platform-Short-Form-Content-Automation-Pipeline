"""
One-time profile setup: banner + bio across YouTube / Facebook / Rumble.
Attaches to the persistent Chrome on port 9222 (ensure_chrome.sh).

Usage:
  python3 setup_profiles.py youtube
  python3 setup_profiles.py facebook
  python3 setup_profiles.py rumble
  python3 setup_profiles.py probe-youtube   # dump page structure for debugging
"""
import sys, time, json, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
BRANDING = ROOT / "branding"
BIO = (BRANDING / "bio.txt").read_text().strip()
BIO_SHORT = BIO.split("\n\n")[1].strip() if "\n\n" in BIO else BIO[:160]
YT_BANNER = str(BRANDING / "youtube_banner.jpg")
FB_COVER = str(BRANDING / "facebook_cover.jpg")
RUMBLE_BANNER = str(BRANDING / "rumble_banner.jpg")
PROFILE_PIC = str(BRANDING / "profile_pic.jpg")

DEBUG_PORT = 9222


def attach():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=3).read()
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{DEBUG_PORT}")
    return webdriver.Chrome(options=opts)


def switch_to_url_substring(driver, substr):
    for h in driver.window_handles:
        driver.switch_to.window(h)
        if substr in driver.current_url:
            return True
    return False


def open_tab(driver, url):
    req = urllib.request.Request(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{url}", method="PUT")
    urllib.request.urlopen(req, timeout=5).read()
    time.sleep(2)
    switch_to_url_substring(driver, url.split("?")[0].split("/")[-1] if "/" in url else url)


def probe_youtube(driver):
    if not switch_to_url_substring(driver, "studio.youtube.com"):
        open_tab(driver, "https://studio.youtube.com/channel/UCQSrcHzHqpkFZjnlBkKrClQ/editing/profile")
        time.sleep(4)
    print("URL:", driver.current_url)
    print("Title:", driver.title)
    # Dump candidate selectors
    js = """
    const out = [];
    for (const el of document.querySelectorAll('input[type=file], button, [role=button], textarea, [contenteditable=true]')) {
      const txt = (el.innerText || el.textContent || '').trim().slice(0, 60);
      const aria = el.getAttribute('aria-label') || '';
      const id = el.id || '';
      const cls = (el.className || '').toString().slice(0, 50);
      const tag = el.tagName.toLowerCase();
      const type = el.getAttribute('type') || '';
      const accept = el.getAttribute('accept') || '';
      if (txt || aria || id) {
        out.push(`${tag}[type=${type}] id=${id} aria='${aria}' txt='${txt}' accept='${accept}' cls='${cls}'`);
      }
    }
    return out.slice(0, 80).join('\\n');
    """
    print(driver.execute_script(js))


def setup_youtube(driver):
    """Upload banner + profile pic, ensure description matches bio.txt, then Publish."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    if not switch_to_url_substring(driver, "studio.youtube.com"):
        open_tab(driver, "https://studio.youtube.com/channel/UCQSrcHzHqpkFZjnlBkKrClQ/editing/profile")
        time.sleep(5)
    if "editing/profile" not in driver.current_url:
        driver.get("https://studio.youtube.com/channel/UCQSrcHzHqpkFZjnlBkKrClQ/editing/profile")
        time.sleep(5)

    print(f"[YT] URL: {driver.current_url}")

    # ----- Banner -----
    print("[YT] Uploading banner...")
    banner_input_js = """
    const hosts = document.querySelectorAll('ytcp-banner-upload');
    for (const h of hosts) {
      const inp = h.shadowRoot ? h.shadowRoot.querySelector('input[type=file]')
                                : h.querySelector('input[type=file]');
      if (inp) return inp;
    }
    return document.querySelector('ytcp-banner-upload input[type=file]');
    """
    banner_input = driver.execute_script(banner_input_js)
    if banner_input:
        banner_input.send_keys(YT_BANNER)
        time.sleep(3)
        # A crop/preview dialog appears — click "Done" / "Select"
        for _ in range(20):
            done = driver.execute_script("""
              const btns = document.querySelectorAll('button, ytcp-button');
              for (const b of btns) {
                const t = (b.innerText||b.textContent||'').trim();
                if (['Done','Select','Save','Apply'].includes(t) && b.offsetParent !== null) return b;
              }
              return null;
            """)
            if done:
                done.click()
                print("[YT] Banner crop dialog confirmed")
                break
            time.sleep(0.5)
    else:
        print("[YT] WARN: banner file input not found")
    time.sleep(2)

    # ----- Profile pic -----
    print("[YT] Uploading profile picture...")
    pic_input = driver.execute_script("""
      const hosts = document.querySelectorAll('ytcp-profile-image-upload');
      for (const h of hosts) {
        const inp = h.shadowRoot ? h.shadowRoot.querySelector('input[type=file]')
                                  : h.querySelector('input[type=file]');
        if (inp) return inp;
      }
      return document.querySelector('ytcp-profile-image-upload input[type=file]');
    """)
    if pic_input:
        pic_input.send_keys(PROFILE_PIC)
        time.sleep(3)
        for _ in range(20):
            done = driver.execute_script("""
              const btns = document.querySelectorAll('button, ytcp-button');
              for (const b of btns) {
                const t = (b.innerText||b.textContent||'').trim();
                if (['Done','Select','Save','Apply'].includes(t) && b.offsetParent !== null) return b;
              }
              return null;
            """)
            if done:
                done.click()
                print("[YT] Profile-pic crop dialog confirmed")
                break
            time.sleep(0.5)
    else:
        print("[YT] WARN: profile-pic file input not found")
    time.sleep(2)

    # ----- Description -----
    print("[YT] Ensuring description matches bio.txt...")
    set_desc_js = """
      const tb = document.querySelector('div#textbox[contenteditable=true]')
              || document.querySelector('[aria-label*="Tell viewers"]');
      if (!tb) return 'no-textbox';
      tb.focus();
      // select all + delete + insert
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, arguments[0]);
      tb.dispatchEvent(new Event('input', {bubbles:true}));
      tb.dispatchEvent(new Event('change', {bubbles:true}));
      return tb.innerText.slice(0, 80);
    """
    result = driver.execute_script(set_desc_js, BIO)
    print(f"[YT] Description set: {result!r}")
    time.sleep(2)

    # ----- Publish -----
    print("[YT] Clicking Publish...")
    pub = driver.execute_script("""
      const btns = document.querySelectorAll('button, ytcp-button');
      for (const b of btns) {
        const aria = b.getAttribute('aria-label') || '';
        const t = (b.innerText||b.textContent||'').trim();
        if ((aria === 'Publish' || t === 'Publish') && b.offsetParent !== null && !b.disabled) return b;
      }
      return null;
    """)
    if pub:
        pub.click()
        time.sleep(4)
        print("[YT] Published ✓")
    else:
        print("[YT] WARN: Publish button not found / disabled — nothing to save?")


FB_PAGE_URL = "https://www.facebook.com/profile.php?id=61590613942018"


def _click_by_predicate(driver, js_predicate_body, label):
    """Find a clickable element via JS predicate and click it. Returns True if clicked."""
    el = driver.execute_script(f"""
      for (const el of document.querySelectorAll('[role=button], button, a, div, span')) {{
        const aria = (el.getAttribute('aria-label')||'').trim();
        const txt = (el.innerText||el.textContent||'').trim();
        if (el.offsetParent === null) continue;
        {js_predicate_body}
      }}
      return null;
    """)
    if el:
        try:
            el.click()
            print(f"[FB] clicked: {label}")
            return True
        except Exception as e:
            # Fallback: JS click
            driver.execute_script("arguments[0].click()", el)
            print(f"[FB] js-clicked: {label} ({e.__class__.__name__})")
            return True
    print(f"[FB] WARN: not found: {label}")
    return False


def setup_facebook(driver):
    """Set FB Page cover photo + bio (intro)."""
    # Close stale FB tabs, open fresh
    to_close = []
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if "facebook.com" in driver.current_url:
                to_close.append(h)
        except Exception:
            pass
    for h in to_close:
        try:
            driver.switch_to.window(h)
            driver.close()
        except Exception:
            pass
    open_tab(driver, FB_PAGE_URL)
    time.sleep(6)
    switch_to_url_substring(driver, "facebook.com/profile.php?id=61590613942018")
    print(f"[FB] URL: {driver.current_url}")

    def cdp_click_aria(aria_or_text):
        """CDP-trusted click on first visible element matching aria-label or innerText."""
        rect = driver.execute_script("""
          for (const el of document.querySelectorAll('[role=button], button, [role=menuitem], div, span, a')) {
            if (el.offsetParent === null) continue;
            const aria = (el.getAttribute('aria-label')||'').trim();
            const txt = (el.innerText||'').trim();
            const target = arguments[0];
            if (aria === target || txt === target) {
              const r = el.getBoundingClientRect();
              if (r.width === 0 || r.height === 0) continue;
              return {x: r.left + r.width/2, y: r.top + r.height/2};
            }
          }
          return null;
        """, aria_or_text)
        if not rect:
            return False
        for ev in ('mouseMoved', 'mousePressed', 'mouseReleased'):
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': ev, 'x': rect['x'], 'y': rect['y'],
                'button': 'left' if ev != 'mouseMoved' else 'none',
                'clickCount': 1 if ev != 'mouseMoved' else 0,
            })
        return True

    # --- Cover photo via OS-level cliclick on the visible buttons ---
    # FB's React rejects all programmatic change events for the cover input.
    # Solution: drive actual mouse + keyboard at the OS level.
    import subprocess

    def click_element_via_os(selector_js, label):
        """Click a DOM element at its actual screen coordinates using cliclick.
        Uses osascript Chrome window bounds + JS innerHeight for accurate offsets."""
        # Scroll element into view first
        driver.execute_script(f"""
          {selector_js}
          if (el) el.scrollIntoView({{block: 'center', inline: 'center'}});
        """)
        time.sleep(0.5)
        rect = driver.execute_script(f"""
          {selector_js}
          if (!el || el.offsetParent === null) return null;
          const r = el.getBoundingClientRect();
          return {{x: r.left + r.width/2, y: r.top + r.height/2}};
        """)
        if not rect:
            print(f"[FB] {label}: element not found")
            return False
        # Chrome window bounds in logical screen coords
        out = subprocess.run([
            "osascript", "-e",
            'tell application "Google Chrome" to get bounds of front window'
        ], capture_output=True, text=True).stdout.strip()
        try:
            win_x, win_y, win_x2, win_y2 = [int(x.strip()) for x in out.split(",")]
        except Exception:
            win_x, win_y, win_x2, win_y2 = 0, 0, 1680, 1050
        info = driver.execute_script("return {iw: window.innerWidth, ih: window.innerHeight};")
        # Viewport bottom = window bottom (Chrome content goes to window bottom)
        viewport_x = win_x  # no side chrome
        viewport_y = win_y2 - info['ih']
        sx = int(viewport_x + rect['x'])
        sy = int(viewport_y + rect['y'])
        print(f"[FB] {label}: viewport=({rect['x']:.0f},{rect['y']:.0f}) screen=({sx},{sy}) window=({win_x},{win_y},{win_x2},{win_y2})")
        subprocess.run(["cliclick", f"c:{sx},{sy}"], check=False)
        return True

    print("[FB] Bringing Chrome to foreground…")
    subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'], check=False)
    time.sleep(1.5)

    print("[FB] OS-clicking 'Add Cover Photo' / 'Edit cover photo'…")
    click_element_via_os("""
      let el = null;
      for (const e of document.querySelectorAll('[role=button], button')) {
        if (e.offsetParent === null) continue;
        const aria = (e.getAttribute('aria-label')||'').trim();
        if (aria === 'Edit cover photo' || aria === 'Add Cover Photo') { el = e; break; }
      }
    """, "cover-edit button")
    time.sleep(2)

    print("[FB] OS-clicking 'Upload photo' menu item…")
    click_element_via_os("""
      let el = null;
      for (const e of document.querySelectorAll('[role=menuitem], div, span')) {
        if (e.offsetParent === null) continue;
        const t = (e.innerText||'').trim();
        if (t === 'Upload photo') { el = e; break; }
      }
    """, "Upload photo menu")
    time.sleep(3)

    print("[FB] Typing cover file path into OS open dialog…")
    subprocess.run(["osascript", "-e", f'''
        tell application "System Events"
            keystroke "g" using {{command down, shift down}}
            delay 0.7
            keystroke "{FB_COVER}"
            delay 0.4
            key code 36
            delay 1.2
            key code 36
        end tell
    '''], check=False)
    time.sleep(6)

    # Possible inline-crop dialog from FB — click Save changes if it appears
    for _ in range(20):
        clicked = driver.execute_script("""
          const dlgs = document.querySelectorAll('div[role=dialog]');
          for (const dlg of dlgs) {
            if (dlg.offsetParent === null) continue;
            const btns = dlg.querySelectorAll('[role=button], button');
            for (const b of btns) {
              if (b.offsetParent === null) continue;
              const t = (b.innerText||'').trim();
              if (/^Save( changes)?$/i.test(t)) { b.click(); return t; }
            }
          }
          return null;
        """)
        if clicked: print(f"[FB] cover Save clicked: {clicked!r}"); break
        time.sleep(0.5)

    # --- Profile picture (same OS keystroke flow) ---
    print("[FB] OS-clicking small camera 'Update profile picture' icon…")
    click_element_via_os("""
      let el = null;
      // Prefer the SMALL camera icon button (~36x36), not the big 168x168 wrap div
      for (const e of document.querySelectorAll('div[aria-label="Update profile picture"], div[aria-label="Add profile picture"]')) {
        if (e.offsetParent === null) continue;
        const r = e.getBoundingClientRect();
        if (r.width > 20 && r.width < 60) { el = e; break; }
      }
    """, "Update profile picture (small icon)")
    time.sleep(2.5)

    print("[FB] OS-clicking 'Upload photo' for profile pic menu…")
    click_element_via_os("""
      let el = null;
      for (const e of document.querySelectorAll('[role=menuitem], div, span')) {
        if (e.offsetParent === null) continue;
        const t = (e.innerText||'').trim();
        if (t === 'Upload photo') { el = e; break; }
      }
    """, "Upload photo (profile pic menu)")
    time.sleep(3)

    print("[FB] Typing profile pic path into OS dialog…")
    subprocess.run(["osascript", "-e", f'''
        tell application "System Events"
            keystroke "g" using {{command down, shift down}}
            delay 0.7
            keystroke "{PROFILE_PIC}"
            delay 0.4
            key code 36
            delay 1.2
            key code 36
        end tell
    '''], check=False)
    time.sleep(6)

    # FB shows an inline crop+Save dialog for profile pics — click Save
    for _ in range(30):
        clicked = driver.execute_script("""
          const dlgs = document.querySelectorAll('div[role=dialog]');
          for (const dlg of dlgs) {
            if (dlg.offsetParent === null) continue;
            const btns = dlg.querySelectorAll('[role=button], button');
            for (const b of btns) {
              if (b.offsetParent === null) continue;
              const t = (b.innerText||'').trim();
              if (/^Save$/i.test(t) || /^Save changes$/i.test(t)) { b.click(); return t; }
            }
          }
          return null;
        """)
        if clicked: print(f"[FB] profile pic Save clicked: {clicked!r}"); break
        time.sleep(0.5)
    time.sleep(4)

    # Wait for crop dialog Save
    saved = False
    for _ in range(80):
        saved = driver.execute_script("""
          const dlgs = document.querySelectorAll('div[role=dialog]');
          for (const dlg of dlgs) {
            if (dlg.offsetParent === null) continue;
            const btns = dlg.querySelectorAll('[role=button], button');
            for (const b of btns) {
              if (b.offsetParent === null) continue;
              const t = (b.innerText||'').trim();
              if (/^Save( changes)?$/i.test(t)) { b.click(); return t; }
            }
          }
          return null;
        """)
        if saved:
            print(f"[FB] Cover crop Save clicked: {saved!r}")
            break
        time.sleep(0.5)
    if not saved:
        print("[FB] WARN: Cover crop Save not found in 40s")
    time.sleep(5)

    # --- Bio / intro ---
    # On FB Pages, profile bio is edited via the "Edit" link beside the bio
    # or via "Edit profile" link on the page header. Try both.
    print("[FB] Opening profile/bio editor...")
    opened = driver.execute_script("""
      const candidates = document.querySelectorAll('a, [role=button]');
      for (const el of candidates) {
        if (el.offsetParent === null) continue;
        const aria = (el.getAttribute('aria-label')||'').trim();
        const txt = (el.innerText||'').trim();
        if (aria === 'Edit profile' || /^Edit profile$/i.test(txt) || /^Edit bio$/i.test(txt)) {
          el.click();
          return aria || txt;
        }
      }
      return null;
    """)
    print(f"[FB] opened editor: {opened!r}")
    time.sleep(4)

    print("[FB] Filling bio field in dialog...")
    short_bio_lines = BIO.split("\n")
    short_bio = next((l for l in short_bio_lines if l.startswith("Powerful")), short_bio_lines[0])[:101]

    bio_result = driver.execute_script("""
      const dialogs = document.querySelectorAll('div[role=dialog]');
      const dlg = dialogs.length ? dialogs[dialogs.length-1] : document;
      // Look for any textarea — FB's bio dialog has a single Bio textarea
      const tas = dlg.querySelectorAll('textarea');
      for (const ta of tas) {
        if (ta.offsetParent === null) continue;
        ta.focus();
        const proto = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        proto.call(ta, arguments[0]);
        ta.dispatchEvent(new Event('input', {bubbles:true}));
        return ta.value.slice(0,80);
      }
      // Fallback: contenteditable
      const ces = dlg.querySelectorAll('[contenteditable=true]');
      for (const ce of ces) {
        if (ce.offsetParent === null) continue;
        ce.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('insertText', false, arguments[0]);
        return (ce.innerText||'').slice(0,80);
      }
      return 'no-field';
    """, short_bio)
    print(f"[FB] Bio set: {bio_result!r}")
    time.sleep(2)

    print("[FB] Clicking Save in bio editor...")
    saved = driver.execute_script("""
      const dialogs = document.querySelectorAll('div[role=dialog]');
      for (const dlg of dialogs) {
        if (dlg.offsetParent === null) continue;
        const btns = dlg.querySelectorAll('[role=button], button');
        for (const b of btns) {
          if (b.offsetParent === null) continue;
          const t = (b.innerText||'').trim();
          if (/^Save$/i.test(t)) { b.click(); return t; }
        }
      }
      return null;
    """)
    print(f"[FB] bio Save clicked: {saved!r}")
    time.sleep(5)
    print("[FB] Done")


def setup_rumble(driver):
    """Set Rumble account profile pic + backsplash banner + about/bio."""
    from selenium.webdriver.common.by import By

    # Close stale rumble account tabs, open profile page fresh
    for h in list(driver.window_handles):
        try:
            driver.switch_to.window(h)
            if "rumble.com/account" in driver.current_url:
                driver.close()
        except Exception:
            pass
    open_tab(driver, "https://rumble.com/account/profile")
    time.sleep(5)
    for h in driver.window_handles:
        driver.switch_to.window(h)
        if "rumble.com/account/profile" in driver.current_url:
            break
    print(f"[Rumble] URL: {driver.current_url}")

    # --- Banner (backsplash) ---
    print("[Rumble] Uploading banner (backsplash)...")
    try:
        banner_inp = driver.find_element(By.CSS_SELECTOR, "input[name=backsplash]")
        # Make hidden file input clickable
        driver.execute_script("""
          arguments[0].style.display='block';
          arguments[0].style.opacity='1';
          arguments[0].style.position='absolute';
          arguments[0].style.top='0';
          arguments[0].style.zIndex='99999';
        """, banner_inp)
        banner_inp.send_keys(RUMBLE_BANNER)
        print("[Rumble] backsplash file sent")
    except Exception as e:
        print(f"[Rumble] backsplash send failed: {e}")
    time.sleep(2)

    # --- Profile picture ---
    print("[Rumble] Uploading profile picture...")
    try:
        pic_inp = driver.find_element(By.CSS_SELECTOR, "input[name=profile_picture]")
        driver.execute_script("""
          arguments[0].style.display='block';
          arguments[0].style.opacity='1';
          arguments[0].style.position='absolute';
          arguments[0].style.top='0';
          arguments[0].style.zIndex='99999';
        """, pic_inp)
        pic_inp.send_keys(PROFILE_PIC)
        print("[Rumble] profile_picture file sent")
    except Exception as e:
        print(f"[Rumble] profile_picture send failed: {e}")
    time.sleep(2)

    # --- About / bio ---
    print("[Rumble] Filling 'about' textarea...")
    rumble_bio_lines = [
        "FrameWise Cinema — daily motivational shorts.",
        "Powerful quotes paired with stunning cinematic footage.",
        "New short every morning at 8:30 AM.",
        "",
        "Watch on YouTube • Rumble • Facebook",
        "#Motivation #Mindset #Inspiration #DailyMotivation #FrameWiseCinema",
    ]
    rumble_bio = "\n".join(rumble_bio_lines)
    result = driver.execute_script("""
      const ta = document.querySelector('textarea[name=additional_info__about]');
      if (!ta) return 'no-textarea';
      ta.focus();
      const proto = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      proto.call(ta, arguments[0]);
      ta.dispatchEvent(new Event('input', {bubbles:true}));
      ta.dispatchEvent(new Event('change', {bubbles:true}));
      return ta.value.slice(0,80);
    """, rumble_bio)
    print(f"[Rumble] about set: {result!r}")
    time.sleep(1)

    # --- Submit ---
    print("[Rumble] Clicking Update...")
    clicked = driver.execute_script("""
      const btns = document.querySelectorAll('input[type=submit], button[type=submit], button');
      for (const b of btns) {
        if (b.offsetParent === null) continue;
        const v = (b.value || b.innerText || '').trim();
        if (/^Update$/i.test(v)) {
          b.click();
          return v;
        }
      }
      return null;
    """)
    print(f"[Rumble] Update clicked: {clicked!r}")
    time.sleep(6)
    print(f"[Rumble] Final URL: {driver.current_url}")
    print("[Rumble] Done ✓")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe-youtube"
    d = attach()
    if cmd == "probe-youtube":
        probe_youtube(d)
    elif cmd == "youtube":
        setup_youtube(d)
    elif cmd == "facebook":
        setup_facebook(d)
    elif cmd == "rumble":
        setup_rumble(d)
    else:
        print(f"Unknown command: {cmd}")
