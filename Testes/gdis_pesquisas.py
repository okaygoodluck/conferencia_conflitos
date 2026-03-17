import os

import gdis_http_extrator


def main():
    data = (os.getenv("GDIS_DATA") or "").strip()
    di = (os.getenv("GDIS_DATA_INICIO") or "").strip()
    df = (os.getenv("GDIS_DATA_FIM") or "").strip()
    if data:
        gdis_http_extrator.DATA_INICIO = data
        gdis_http_extrator.DATA_FIM = data
    elif di or df:
        gdis_http_extrator.DATA_INICIO = di or df
        gdis_http_extrator.DATA_FIM = df or di
    gdis_http_extrator.main()


if __name__ == "__main__":
    main()

