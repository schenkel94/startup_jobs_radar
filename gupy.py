import streamlit as st
import requests
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="Gupy Hunter 2026", layout="wide")


def buscar_vagas_gupy(termo):
    vagas_lista = []

    url = "https://employability-portal.gupy.io/api/v1/jobs"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    # paginação (até ~200 vagas)
    for page in range(1, 5):

        params = {
            "jobName": termo,
            "offset": (page - 1) * 50,
            "limit": 50,
            "sortBy": "publishedDate",
            "sortOrder": "desc"
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=20
            )

            if response.status_code != 200:
                continue

            dados = response.json()
            jobs = dados.get("data", [])

            for vaga in jobs:

                data_iso = vaga.get("publishedDate")

                if data_iso:
                    try:
                        dt_obj = datetime.fromisoformat(
                            data_iso.replace("Z", "")
                        )
                    except:
                        dt_obj = datetime.min
                else:
                    dt_obj = datetime.min

                # normalizar modalidade
                workplace = vaga.get("workplaceType") or ""
                workplace = workplace.upper()

                if workplace == "REMOTE" or vaga.get("isRemoteWork"):
                    modalidade = "Remoto"
                elif workplace == "HYBRID":
                    modalidade = "Híbrido"
                elif workplace in ["ONSITE", "ON-SITE"]:
                    modalidade = "Presencial"
                else:
                    modalidade = "Indefinido"

                vagas_lista.append({
                    "data_dt": dt_obj,
                    "Data": dt_obj.strftime('%d/%m/%Y') if dt_obj != datetime.min else "",
                    "Empresa": vaga.get("careerPageName", "").upper(),
                    "Vaga": vaga.get("name", ""),
                    "Modalidade": modalidade,
                    "Link": vaga.get("jobUrl", f"https://portal.gupy.io/jobs/{vaga.get('id')}")
                })

        except Exception as e:
            st.error(f"Erro ao buscar página {page}: {e}")

    vagas_lista.sort(key=lambda x: x["data_dt"], reverse=True)

    return vagas_lista


# ------------------------
# Interface
# ------------------------

st.title("🕵️ Schenkel JobSearch Gupy Portal")

with st.sidebar:
    st.header("Configurações")

    termo = st.text_input(
        "Buscar por:",
        value="Analista de Dados"
    )

    apenas_remoto = st.toggle(
        "Apenas Remoto",
        value=True
    )


if st.button("🚀 Escanear Portal Gupy", use_container_width=True):

    with st.spinner("Buscando vagas fresquinhas..."):

        resultados = buscar_vagas_gupy(termo)

        if apenas_remoto:
            resultados = [
                v for v in resultados
                if v["Modalidade"] == "Remoto"
            ]

        if resultados:

            st.metric(
                "Vaga mais recente encontrada em:",
                resultados[0]["Data"]
            )

            for v in resultados:

                with st.container():

                    col1, col2, col3, col4 = st.columns([1, 4, 2, 2])

                    with col1:

                        # destaque para vagas do mês atual
                        hoje = datetime.now()

                        if v["data_dt"].month == hoje.month and v["data_dt"].year == hoje.year:
                            st.success(f"**{v['Data']}**")
                        else:
                            st.write(v["Data"])

                    with col2:
                        st.markdown(f"**{v['Vaga']}**")
                        st.caption(f"🏢 {v['Empresa']}")

                    with col3:
                        st.write(f"🌍 {v['Modalidade']}")

                    with col4:
                        st.link_button(
                            "Abrir Vaga",
                            v["Link"],
                            use_container_width=True
                        )

                    st.divider()

        else:
            st.warning("Nenhuma vaga encontrada para este termo.")