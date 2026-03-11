import streamlit as st
import pandas as pd

from crawler_universal import crawl_empresas


st.set_page_config(page_title="Radar de Vagas Startups", layout="wide")

st.title("🚀 Radar de Vagas de Startups")

st.caption("Crawler de vagas ocultas antes de aparecer no LinkedIn")


# carregar empresas
with open("empresas.txt") as f:
    empresas = [e.strip() for e in f.readlines()]


# filtros
st.sidebar.header("Filtros")

cargo_filtro = st.sidebar.text_input(
    "Filtrar cargo (ex: data, analyst, engineer)"
)

empresa_filtro = st.sidebar.multiselect(
    "Filtrar empresas",
    empresas
)


# botão crawler
if st.button("🔎 Buscar vagas"):

    with st.spinner("Escaneando startups..."):

        vagas = crawl_empresas(empresas)

        df = pd.DataFrame(vagas)

        if df.empty:
            st.warning("Nenhuma vaga encontrada")
            st.stop()


        # filtro empresa
        if empresa_filtro:

            df = df[df["empresa"].isin(empresa_filtro)]


        # filtro cargo
        if cargo_filtro:

            df = df[
                df["vaga"].str.lower().str.contains(
                    cargo_filtro.lower(),
                    na=False
                )
            ]


        st.success(f"{len(df)} vagas encontradas")


        df = df.drop_duplicates(subset=["link"])


        st.dataframe(df, use_container_width=True)


        # export excel
        excel = df.to_excel("vagas.xlsx", index=False)


        st.download_button(
            "📥 Baixar Excel",
            df.to_csv(index=False),
            "vagas_startups.csv"
        )
