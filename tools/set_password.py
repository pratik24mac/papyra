"""Change the app's fixed sign-in credentials.  Usage: set_password.py <username> <new-password>
Rewrites the constants in apps/desktop/src-tauri/src/auth.rs; rebuild the app afterwards."""
import hashlib, re, sys
from pathlib import Path
user, pw = sys.argv[1], sys.argv[2]
if len(pw) < 10: sys.exit("use at least 10 characters")
p = Path(__file__).resolve().parents[1] / "apps/desktop/src-tauri/src/auth.rs"
s = p.read_text()
s = re.sub(r'pub const USERNAME: &str = "[^"]*";', f'pub const USERNAME: &str = "{user}";', s)
s = re.sub(r'const PASSWORD_SHA256: &str = "[0-9a-f]+";', f'const PASSWORD_SHA256: &str = "{hashlib.sha256(f"docmaster-v1:{pw}".encode()).hexdigest()}";', s)
s = re.sub(r'assert!\(verify\("[^"]*", "[^"]*"\)\);', f'assert!(verify("{user}", "{pw}"));', s, count=1)
p.write_text(s); print("updated auth.rs — rebuild the app (npm run tauri dev / tauri build)")
