![Streamseeker usage](https://raw.githubusercontent.com/Denfie/streamseeker/master/assets/usage-v-0-1-2.gif)

### venv cheat sheet

StreamSeeker setzt Standard-`pip` + `venv` voraus, kein Poetry mehr.

```bash
# Dev-venv aufsetzen
python3 -m venv .venv
source .venv/bin/activate           # Linux / macOS
# .\.venv\Scripts\activate          # Windows

# Paket + Test-Deps editable installieren
pip install -e '.[dev]'

# Umgebung abschießen
deactivate
rm -rf .venv
```

Troubleshooting: falls `python -m venv .venv` mit einem
`ensurepip`-Fehler abbricht, ist meist eine Python-Kern-Installation
ohne `ensurepip` die Ursache (bei Debian-basierten Distros oft als
separates `python3-venv`-Paket nachzuinstallieren).
