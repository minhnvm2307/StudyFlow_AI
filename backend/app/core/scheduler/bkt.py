from app.schemas import Topic

class BKTModel:
    """
    Binary-outcome BKT update.

    State:  P(L)  — probability the student has mastered the concept.
    Params: P(T)  — transition (learn on practice),
            P(G)  — guess (correct without mastery),
            P(S)  — slip  (incorrect despite mastery).

    Cold-start priors aligned with the current C2 spec:
        P(L_0)=0.05, P(T)=0.2, P(G)=0.2, P(S)=0.1
    """

    DIAGNOSTIC_PRIORS = {"p_l0": 0.05, "p_t": 0.2, "p_g": 0.20, "p_s": 0.1}
    NORMAL_PRIORS     = {"p_l0": 0.05, "p_t": 0.2, "p_g": 0.20, "p_s": 0.1}

    @staticmethod
    def predict_p_correct(topic: Topic) -> float:
        """
        P(C_i) = P(L_i)*(1-P(S)) + (1-P(L_i))*P(G)
        """
        return topic.mastery * (1 - topic.p_s) + (1 - topic.mastery) * topic.p_g

    @staticmethod
    def update(topic: Topic, correct: bool) -> dict:
        """
        Update mastery in-place and return BKT transaction details.

        P(L|correct)   = [ P(L)*(1-P(S)) ] / [ P(L)*(1-P(S)) + (1-P(L))*P(G) ]
        P(L|incorrect) = [ P(L)*P(S)     ] / [ P(L)*P(S)     + (1-P(L))*(1-P(G)) ]
        P(L_new)       = P(L_obs) + (1 - P(L_obs)) * P(T)
        """
        p_l, p_t, p_g, p_s = topic.mastery, topic.p_t, topic.p_g, topic.p_s
        predicted = BKTModel.predict_p_correct(topic)

        if correct:
            p_l_obs = (p_l * (1 - p_s)) / max(1e-9, (p_l * (1 - p_s)) + (1 - p_l) * p_g)
        else:
            p_l_obs = (p_l * p_s) / max(1e-9, (p_l * p_s) + (1 - p_l) * (1 - p_g))

        p_l_new = p_l_obs + (1 - p_l_obs) * p_t
        topic.mastery = max(0.01, min(0.99, p_l_new))

        return {
            "p_l_before": p_l,
            "p_t_used": p_t,
            "p_g_used": p_g,
            "p_s_used": p_s,
            "predicted_p_correct": predicted,
            "p_l_obs": p_l_obs,
            "p_l_after": topic.mastery,
        }

    @staticmethod
    def init_diagnostic(topic: Topic):
        """Apply cold-start diagnostic priors (Edge-case #5)."""
        p = BKTModel.DIAGNOSTIC_PRIORS
        topic.mastery = p["p_l0"]
        topic.p_l0    = p["p_l0"]
        topic.p_t     = p["p_t"]
        topic.p_g     = p["p_g"]
        topic.p_s     = p["p_s"]
        topic.awaiting_diagnostic = True

# Backwards-compat aliases (used by existing tests)
BKTModel.update_mastery = staticmethod(lambda topic, correct: BKTModel.update(topic, correct)["p_l_after"])
