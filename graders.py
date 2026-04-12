def easy_grader(trajectory: dict = None) -> float:
    """
    Grades an easy episode trajectory for the ChipForge environment.
    Takes a trajectory dictionary and returns a strict [0.0, 1.0] score.
    """
    if trajectory is None:
        trajectory = {}
        
    rewards = trajectory.get("rewards", [])
    if not rewards:
        return 0.50  # Neutral score instead of 0.0
        
    total = sum(rewards)
    normalized = (total + 0.5) / 1.5
    return max(0.010, min(0.990, round(normalized, 4)))

def medium_grader(trajectory: dict = None) -> float:
    """
    Grades a medium episode trajectory for the ChipForge environment.
    Takes a trajectory dictionary and returns a strict [0.0, 1.0] score.
    """
    if trajectory is None:
        trajectory = {}
        
    rewards = trajectory.get("rewards", [])
    if not rewards:
        return 0.50  # Neutral score instead of 0.0
        
    total = sum(rewards)
    normalized = (total + 0.5) / 1.5
    return max(0.010, min(0.990, round(normalized, 4)))

def hard_grader(trajectory: dict = None) -> float:
    """
    Grades a hard episode trajectory for the ChipForge environment.
    Takes a trajectory dictionary and returns a strict [0.0, 1.0] score.
    """
    if trajectory is None:
        trajectory = {}
        
    rewards = trajectory.get("rewards", [])
    if not rewards:
        return 0.50  # Neutral score instead of 0.0
        
    total = sum(rewards)
    normalized = (total + 0.5) / 1.5
    return max(0.010, min(0.990, round(normalized, 4)))
