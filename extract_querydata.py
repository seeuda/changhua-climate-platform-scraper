#!/usr/bin/env python3
"""Extract the embedded QueryData JSON from a saved page snapshot.

The platform embeds its document list as
    var QueryData = JSON.parse('...escaped json...');
and renders it client-side, which is why the static HTML contains no
File/Get anchors. This tool pulls that JSON out, saves it to
data/querydata.json, and prints a compact structure summary to paste
back to the developer.

Run: python extract_querydata.py
"""

import json
import re
import sys
from pathlib import Path

# Windows cmd defaults to a legacy codepage; force UTF-8 output so
# Chinese text is readable instead of mojibake.
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SNAPSHOT = Path('data/snapshots/page_1.html')
OUTPUT = Path('data/querydata.json')


def read_js_string(src: str, start: int, quote: str):
    """Read a JS string literal starting after its opening quote."""
    out = []
    i = start
    while i < len(src):
        c = src[i]
        if c == '\\':
            out.append(src[i:i + 2])
            i += 2
            continue
        if c == quote:
            return ''.join(out), i
        out.append(c)
        i += 1
    raise ValueError('unterminated string literal')


def unescape_js(s: str) -> str:
    """Decode JS string escapes without mangling raw non-ASCII text."""
    def repl(m):
        esc = m.group(1)
        if esc.startswith('u'):
            return chr(int(esc[1:], 16))
        if esc.startswith('x'):
            return chr(int(esc[1:], 16))
        return {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f',
                '0': '\0', "'": "'", '"': '"', '\\': '\\', '/': '/'}.get(esc, esc)
    return re.sub(r'\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)', repl, s)


def summarize(value, depth=0):
    pad = '  ' * depth
    if isinstance(value, list):
        print(f"{pad}list of {len(value)} items")
        if value:
            summarize(value[0], depth + 1)
    elif isinstance(value, dict):
        print(f"{pad}dict keys: {list(value.keys())}")
        for k, v in list(value.items())[:12]:
            if isinstance(v, (list, dict)):
                print(f"{pad}  {k}:")
                summarize(v, depth + 2)
            else:
                text = str(v)
                text = text[:90] + '…' if len(text) > 90 else text
                print(f"{pad}  {k} = {text!r}")
    else:
        text = str(value)
        print(f"{pad}{text[:90]}")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else SNAPSHOT
    if not path.exists():
        print(f"Snapshot not found: {path} — run: python main.py first")
        return 1

    html = path.read_text(encoding='utf-8', errors='replace')
    print("=" * 62)
    print(f"QUERYDATA EXTRACTION: {path} ({len(html):,} bytes)")
    print("=" * 62)

    # Decisive quick check: are File/Get URLs hiding in the raw HTML/JS?
    for needle in ('File/Get', 'File\\/Get', 'FileGet', '.pdf', '.PDF'):
        count = html.count(needle)
        if count:
            print(f"[raw contains {needle!r}] {count} times")

    found = []
    for m in re.finditer(r'(\w+)\s*=\s*JSON\.parse\(\s*(["\'])', html):
        var_name, quote = m.group(1), m.group(2)
        try:
            raw, _ = read_js_string(html, m.end(), quote)
            data = json.loads(unescape_js(raw))
            found.append((var_name, data))
        except (ValueError, json.JSONDecodeError) as e:
            print(f"\n[{var_name}] failed to parse: {e}")

    if not found:
        print("\nNo JSON.parse(...) payloads recovered. Paste this output back.")
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    dump = {name: data for name, data in found}
    OUTPUT.write_text(json.dumps(dump, ensure_ascii=False, indent=2),
                      encoding='utf-8')

    for name, data in found:
        print(f"\n[variable] {name}")
        summarize(data)
        if isinstance(data, list) and len(data) > 1:
            print("  --- second item ---")
            summarize(data[1], 1)
        if isinstance(data, dict):
            # If it wraps a list (e.g. {"Total":346,"Items":[...]}) show it
            for k, v in data.items():
                if isinstance(v, list) and v:
                    print(f"  --- first item of {name}.{k} "
                          f"(list of {len(v)}) ---")
                    summarize(v[0], 1)

    print(f"\nFull payload saved to {OUTPUT}")
    print("=" * 62)
    print("END — paste everything above back for analysis")
    print("=" * 62)
    return 0


if __name__ == '__main__':
    sys.exit(main())
