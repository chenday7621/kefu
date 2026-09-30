"""Aggregate official scorer values supplied by the caller; no private labels."""
def summarize_rewards(rewards):
    values = list(rewards)
    if not values:
        raise ValueError("No scored trials")
    if any(not isinstance(x, (int, float)) or isinstance(x, bool) or not 0 <= x <= 1 for x in values):
        raise ValueError("Expected official numeric rewards in [0, 1]")
    return {"task_count": len(values), "success_count": sum(x == 1 for x in values),
            "task_success_rate": sum(x == 1 for x in values) / len(values),
            "mean_reward": sum(values) / len(values)}
