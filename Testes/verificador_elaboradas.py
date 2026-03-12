import os
import subprocess
import sys


def main():
    env = dict(os.environ)
    subprocess.run([sys.executable, "verificador_elaboradas.py"], env=env)


if __name__ == "__main__":
    main()

