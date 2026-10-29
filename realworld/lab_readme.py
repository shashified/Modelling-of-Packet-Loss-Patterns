"""The 'Read me' panel in the Real Network Lab sidebar: how the project works, every formula, every decision rule."""
import streamlit as st

from src import config as C


def tex(f):
    st.latex(r"\footnotesize " + f)


def render():
    with st.sidebar.expander("📖 Read me: how this works", expanded=False):
        st.markdown("#### The project in one minute")
        st.markdown(
            "**Question.** Textbook formulas treat every lost packet as an independent coin flip. "
            "Is that true, and what goes wrong if it is not?\n\n"
            "**Phase 1 (case study).** Three networks simulated with the Gilbert-Elliott model "
            "(a Good state with rare loss and a Bad state with heavy loss). Because the true answer is known, "
            "every test and interval could be checked.\n\n"
            "**Phase 2 (this page).** The laptop sends 50 numbered packets per second (one every 20 ms, like a "
            "voice call) to the router or a server. A packet whose reply has not come back within "
            f"2 s is **lost**. The run becomes a list of 0s (delivered) and 1s (lost), and the same "
            "statistics as Phase 1 run on it. Then the real numbers are set next to the study's.")
        st.markdown("**From packets to numbers**")
        st.markdown(
            f"- **Windows:** losses are counted in {C.WINDOW_S:g}-second windows (50 packets each).\n"
            f"- **Blocks:** {C.BLOCK_S}-second blocks (500 packets) for the design effect.\n"
            "- **Gaps:** seconds between one loss and the next.\n"
            "- **Transitions:** what came after each delivered packet (N) and each lost packet (L).")

        st.markdown("#### Formulas")
        st.markdown("**Loss rate and Bayesian estimate (O5)**")
        tex(r"\hat p=\frac{k}{n}")
        tex(r"p\mid\text{data}\sim")
        tex(r"\mathrm{Beta}(1+k,\;1+n-k)")
        st.caption("k losses in n packets, flat Beta(1, 1) prior. 95% credible interval = 2.5% and 97.5% quantiles.")
        st.markdown("**Losses per second (O1)**")
        tex(r"D=\frac{s^2}{\bar x}")
        tex(r"(m-1)\,D\sim\chi^2_{m-1}\ \text{if Poisson}")
        tex(r"\chi^2=\sum\frac{(O-E)^2}{E}")
        tex(r"\mathrm{AIC}=2k_{\text{par}}-2\ln L")
        st.caption("D = 1 for random loss. Bins with expected count below 5 are pooled. Lower AIC wins "
                   "(Poisson has 1 parameter, Negative Binomial 2).")
        st.markdown("**Gaps between losses (O2)**")
        tex(r"S_{\exp}(t)=e^{-\lambda t}")
        tex(r"S_{2}(t)=w\,e^{-\lambda_1 t}")
        tex(r"\qquad+(1-w)\,e^{-\lambda_2 t}")
        tex(r"D_{KS}=\sup_t\,|F_n(t)-F(t)|")
        st.caption("Two-phase parameters by the EM algorithm. KS p-value by parametric bootstrap, because λ is "
                   "estimated from the same data.")
        st.markdown("**Does one loss pull in the next? (O3)**")
        tex(r"a=P(L\mid N)=\frac{n_{NL}}{n_{N\cdot}}")
        tex(r"b=P(L\mid L)=\frac{n_{LL}}{n_{L\cdot}}")
        tex(r"E[R]=1+\frac{2n_0n_1}{n}")
        tex(r"z=\frac{R-E[R]}{\sqrt{\mathrm{Var}(R)}}")
        tex(r"G^2=2(\ell_{1}-\ell_{0})\sim\chi^2_1")
        tex(r"\text{mean burst}=\frac{1}{1-b}")
        tex(r"\pi_L=\frac{a}{a+1-b}")
        st.caption("R = number of runs of identical outcomes; ℓ₁, ℓ₀ = log-likelihood of the Markov and independent models. b/a = 1 means independent. G² follows χ²(1) by "
                   "Wilks' theorem. a and b also get Beta posteriors.")
        st.markdown("**Comparing networks (O4)**")
        tex(r"H=\frac{12}{N(N+1)}\sum_j\frac{R_j^2}{n_j}")
        tex(r"\qquad-3(N+1)")
        tex(r"p_{\text{Bonf}}=\min(1,\,m\,p)")
        st.caption("Kruskal-Wallis on losses per second, Mann-Whitney U for pairs, χ² test of equal loss "
                   "proportions, and P(p₁ < p₂ < …) from posterior draws.")
        st.markdown("**Honest interval (O6)**")
        tex(r"\mathrm{deff}=\frac{s^2_{\text{block}}}{m\,\hat p(1-\hat p)}")
        tex(r"n_{\text{eff}}=\frac{n}{\mathrm{deff}}")
        tex(r"p\sim\mathrm{Beta}(1+k',\,1+n'-k')")
        tex(r"k'=k/\mathrm{deff},\;\; n'=n/\mathrm{deff}")
        st.caption("m = 500 packets per block. Coverage = share of simulated runs whose 95% interval holds the "
                   "true rate. Power = share in which the runs test detects the bursts.")

        st.markdown("#### Decision rules")
        st.markdown(
            f"- Significance level **α = {C.ALPHA}**: reject when p < 0.05.\n"
            "- Tests run only with **at least 10 losses**; fewer means 'too few losses to test'.\n"
            "- Verdict **bursty** if the runs test rejects with z < 0, **or** the Markov test rejects and "
            "P(b > a) > 0.975. Otherwise **no evidence of bursts**.\n"
            "- Poisson rejected if the dispersion or χ² test has p < 0.05; the better model has lower AIC.\n"
            "- Exponential gaps rejected if the bootstrap KS p < 0.05.\n"
            f"- A **heavy second** has {C.HEAVY_LOSS_K} or more losses (posterior predictive check).\n"
            f"- A capture is **long enough** when the runs test's power reaches {C.POWER_TARGET:g}.\n"
            "- An interval is **trustworthy** when its coverage is close to 95%.\n"
            "- **Live vs study:** a real run tells the same story as the study when both reach the same "
            "verdict on each test; the loss rates agree when the study's rate lies inside the run's interval.")

        st.markdown("#### What we assumed vs what we found")
        st.markdown(
            "| Assumed | Found |\n|---|---|\n"
            "| Losses are independent | A loss makes the next one 31–43× likelier |\n"
            "| Losses per second are Poisson | Variance is 1.6–10× the mean |\n"
            "| Gaps are exponential | Two time scales: inside and between bursts |\n"
            "| Usual 95% interval is fine | It held the truth only 40–86% of the time |\n"
            "| A short capture is enough | Wired needs about 5 min to see bursts |")
        st.caption("Why, and how your own runs compare: the **🧠 Assumptions vs findings** tab.")
