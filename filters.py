KEYWORDS_DADOS = [
"data",
"analytics",
"machine learning",
"ai",
"cientista",
"analista",
"bi",
"data engineer"
]

def filtrar_vagas(vagas):

    resultado = []

    for v in vagas:

        titulo = v["vaga"].lower()

        if any(k in titulo for k in KEYWORDS_DADOS):

            local = str(v["local"]).lower()

            if "remot" in local or local == "":
                resultado.append(v)

    return resultado
