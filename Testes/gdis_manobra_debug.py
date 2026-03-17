import os
import subprocess
import sys


def main():
    numero = (os.getenv("GDIS_MANOBRA") or "").strip()
    if not numero:
        numero = input("Manobra: ").strip()
    if not numero:
        print("Manobra vazia.")
        return

    env = dict(os.environ)
    env["GDIS_MANOBRA"] = numero
    subprocess.run([sys.executable, "gdis_manobra_debug.py"], env=env)


if __name__ == "__main__":
    main()

