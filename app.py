import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Simulador de Renda Fixa", page_icon="📈")


@st.cache_data(ttl=3600)
def bcb(serie: int, padrao: float):
    try:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json"
        return float(requests.get(url, timeout=5).json()[0]["valor"]), True
    except Exception:
        return padrao, False


def aliquota(dias):
    return np.select([dias <= 180, dias <= 360, dias <= 720], [0.225, 0.20, 0.175], default=0.15)


def _estado(inicial, mensal, t, r, isento):
    prazos = np.concatenate(([t], t - np.arange(1, t + 1)))
    valores = np.concatenate(([inicial], np.full(t, mensal)))
    bruto = valores * (1 + r) ** prazos
    ir = 0.0 if isento else float(((bruto - valores) * aliquota(prazos * 30)).sum())
    return valores.sum(), bruto.sum(), ir


def simulate(inicial, mensal, meses, taxa_aa, isento):
    r = (1 + taxa_aa) ** (1 / 12) - 1
    linhas = [(t, *_estado(inicial, mensal, t, r, isento)) for t in range(meses + 1)]
    df = pd.DataFrame(linhas, columns=["mes", "investido", "bruto", "ir"]).set_index("mes")
    df["liquido"] = df["bruto"] - df["ir"]
    return df


def aporte_necessario(meta, inicial, meses, taxa_aa, isento):
    r = (1 + taxa_aa) ** (1 / 12) - 1
    lo, hi = 0.0, float(meta)
    for _ in range(30):
        mid = (lo + hi) / 2
        _, bruto, ir = _estado(inicial, mid, meses, r, isento)
        lo, hi = (lo, mid) if bruto - ir >= meta else (mid, hi)
    return hi


def brl(x):
    return "R$ " + f"{x:,.0f}".replace(",", ".")


selic0, ok1 = bcb(432, 14.50)
ipca0, ok2 = bcb(13522, 4.50)

st.title("Simulador de Renda Fixa")
st.caption("Simulação educativa, não é recomendação de investimento.")
st.caption("Criado por Bruno Muniz")

with st.expander("Premissas de mercado (editáveis)"):
    st.caption("Taxas atualizadas pelo Banco Central." if (ok1 and ok2) else "Sem conexão com o BC: valores padrão, edite abaixo.")
    c1, c2 = st.columns(2)
    selic = c1.number_input("Selic (% a.a.)", value=float(selic0), step=0.25)
    ipca = c2.number_input("IPCA (% a.a.)", value=float(ipca0), step=0.25)
    pre = c1.number_input("Taxa prefixada (% a.a.)", value=13.0, step=0.25)
    cupom = c2.number_input("Cupom IPCA+ (% a.a.)", value=7.0, step=0.25)
    pct_cdi = c1.number_input("CDB/LCI-LCA (% do CDI)", value=100.0, step=5.0)
    cdi = selic - 0.10

ATIVOS = {
    "Tesouro Selic": (selic / 100, False),
    "Tesouro Prefixado": (pre / 100, False),
    "Tesouro IPCA+": ((1 + ipca / 100) * (1 + cupom / 100) - 1, False),
    "CDB": (pct_cdi / 100 * cdi / 100, False),
    "LCI/LCA (isento de IR)": (pct_cdi / 100 * cdi / 100, True),
}
POUPANCA = 1.005**12 - 1

inicial = st.number_input("Aporte inicial (R$)", value=1000.0, step=100.0)
mensal = st.number_input("Aporte mensal (R$)", value=200.0, step=50.0)
ativo = st.selectbox("Ativo", list(ATIVOS))
taxa, isento = ATIVOS[ativo]
st.caption(f"Taxa bruta usada: {taxa * 100:.2f}% a.a.")

aba1, aba2, aba3 = st.tabs(["Valor futuro", "Objetivo", "Viver de renda"])

with aba1:
    anos = st.slider("Prazo (anos)", 1, 40, 5)
    real = st.checkbox("Mostrar em poder de compra de hoje")
    meses = anos * 12
    df = simulate(inicial, mensal, meses, taxa, isento)
    poup = simulate(inicial, mensal, meses, POUPANCA, True)
    fator = (1 + ipca / 100) ** (-df.index / 12) if real else 1.0
    st.caption("Valores em poder de compra de hoje (deflacionados pelo IPCA)." if real else "Valores nominais.")

    fim = df.iloc[-1]
    ff = fator[-1] if real else 1
    c1, c2 = st.columns(2)
    c1.metric("Total investido", brl(fim.investido))
    c2.metric("Saldo bruto", brl(fim.bruto * ff))
    c1.metric("Imposto (IR)", brl(fim.ir))
    c2.metric("Saldo líquido", brl(fim.liquido * ff))
    st.metric("Vs. poupança (líquido)", brl((fim.liquido - poup.liquido.iloc[-1]) * ff))

    graf = pd.DataFrame({
        "Capital investido": df.investido,
        "Saldo líquido": df.liquido * fator,
        "Poupança (ref.)": poup.liquido * fator,
    })
    graf.index = graf.index / 12
    graf.index.name = "Anos"
    st.line_chart(graf)

with aba2:
    meta = st.number_input("Meta de patrimônio líquido (R$)", value=100000.0, step=5000.0)
    longo = simulate(inicial, mensal, 600, taxa, isento)
    atingiu = longo.index[longo.liquido >= meta]
    if len(atingiu):
        m = int(atingiu[0])
        st.metric("Tempo para atingir a meta", f"{m // 12} anos e {m % 12} meses")
    else:
        st.warning("Com esses aportes a meta não é atingida em 50 anos.")
    prazo_meta = st.slider("Ou: em quantos anos você quer chegar lá?", 1, 40, 10)
    st.metric(f"Aporte mensal necessário em {prazo_meta} anos", brl(aporte_necessario(meta, inicial, prazo_meta * 12, taxa, isento)))

with aba3:
    renda = st.number_input("Renda mensal desejada (R$ de hoje)", value=5000.0, step=500.0)
    taxa_liq = taxa if isento else taxa * (1 - 0.15)
    taxa_real = (1 + taxa_liq) / (1 + ipca / 100) - 1
    if taxa_real <= 0:
        st.warning("A taxa real líquida é zero ou negativa: nenhum patrimônio sustenta essa renda sem consumir o principal.")
    else:
        st.metric("Patrimônio necessário", brl(renda * 12 / taxa_real))
        st.caption(f"Taxa real líquida: {taxa_real * 100:.2f}% a.a.")
