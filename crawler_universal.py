import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def crawl_inhire(empresa):

    vagas = []

    endpoints = [
        f"https://{empresa}.inhire.app/api/jobs",
        f"https://{empresa}.inhire.app/api/v1/jobs"
    ]

    for url in endpoints:

        try:

            r = requests.get(url, headers=HEADERS, timeout=10)

            if r.status_code != 200:
                continue

            data = r.json()

            for job in data:

                vagas.append({
                    "empresa": empresa,
                    "vaga": job.get("title",""),
                    "local": job.get("location",""),
                    "link": f"https://{empresa}.inhire.app/vagas/{job.get('slug','')}"
                })

            if vagas:
                break

        except:
            continue

    return vagas


def crawl_empresas(empresas):

    todas = []

    for empresa in empresas:

        print("Escaneando:", empresa)

        vagas = crawl_inhire(empresa)

        todas.extend(vagas)

    return todas
