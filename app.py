import streamlit as st
import pandas as pd

from crawler_universal import crawl_empresas
from filters import filtrar_vagas
from storage import salvar_dataset, carregar_dataset


st.set_page_config(page_title="Radar de Vagas de Startups", layout="wide")

st.title("🚀 Radar de Vagas de Startups")

st.write("Encontre vagas escondidas antes de aparecerem no LinkedIn")


# carregar empresas
with open("empresas.txt") as f:
    empresas = [e.strip() for e in f.readlines()]


# botão de coleta
if st.button("🔎 Atualizar vagas"):

    with st.spinner("Coletando vagas..."):

        vagas = crawl_empresas(empresas)

        vagas = filtrar_vagas(vagas)

if vagas:
    df = salvar_dataset(vagas)
else:
    df = carregar_dataset()

    st.success("ETL concluído!")

else:

    df = carregar_dataset()


if not df.empty:

    col1, col2 = st.columns(2)

    col1.metric("Total vagas", len(df))

    col2.metric("Vagas novas", df["nova_vaga"].sum())


    st.dataframe(df, use_container_width=True)


    st.download_button(
        "Baixar dataset",
        df.to_csv(index=False, sep=";"),
        "vagas_startups.csv"
    )

else:

    st.info("Nenhuma vaga encontrada ainda.")
