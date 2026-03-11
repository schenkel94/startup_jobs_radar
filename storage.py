import pandas as pd
import os
from datetime import datetime

DATASET = "data/dataset_jobs.csv"


def salvar_dataset(vagas):

    hoje = datetime.now().strftime("%Y-%m-%d")

    df = pd.DataFrame(vagas)

    df["data_etl"] = hoje

    if os.path.exists(DATASET):

        antigo = pd.read_csv(DATASET)

        antigos_links = set(antigo["link"])

        df["nova_vaga"] = ~df["link"].isin(antigos_links)

        df = pd.concat([antigo, df])

    else:

        df["nova_vaga"] = True

    df.to_csv(DATASET, index=False, sep=";")

    return df


def carregar_dataset():

    if os.path.exists(DATASET):

        return pd.read_csv(DATASET, sep=";")

    else:

        return pd.DataFrame(columns=[
            "empresa",
            "vaga",
            "local",
            "link",
            "data_etl",
            "nova_vaga"
        ])
