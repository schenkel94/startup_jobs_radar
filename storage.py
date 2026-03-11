import pandas as pd
import os
from datetime import datetime

DATASET = "data/dataset_jobs.csv"


COLUNAS = [
    "empresa",
    "vaga",
    "local",
    "link",
    "data_etl",
    "nova_vaga"
]


def salvar_dataset(vagas):

    hoje = datetime.now().strftime("%Y-%m-%d")

    df = pd.DataFrame(vagas)

    if df.empty:
        df = pd.DataFrame(columns=COLUNAS)

    df["data_etl"] = hoje

    # se dataset existe e não está vazio
    if os.path.exists(DATASET) and os.path.getsize(DATASET) > 0:

        antigo = pd.read_csv(DATASET, sep=";")

        antigos_links = set(antigo["link"])

        df["nova_vaga"] = ~df["link"].isin(antigos_links)

        df = pd.concat([antigo, df], ignore_index=True)

    else:

        df["nova_vaga"] = True

    os.makedirs("data", exist_ok=True)

    df.to_csv(DATASET, index=False, sep=";")

    return df


def carregar_dataset():

    if os.path.exists(DATASET) and os.path.getsize(DATASET) > 0:

        return pd.read_csv(DATASET, sep=";")

    else:

        return pd.DataFrame(columns=COLUNAS)
