def chipforge_grader(trajectory: dict = None) -> float:
    """
    Grades an episode trajectory for the ChipForge environment.
    Takes a trajectory dictionary and returns a strict [0.0, 1.0] score.
    """
    if trajectory is None:
        trajectory = {}
        
    rewards = trajectory.get("rewards", [])
    if not rewards:
        return 0.50  # Neutral score instead of 0.0
        
    # ChipForge rewards scale roughly between -0.4 and 1.1 based on
    # initial potential, step penalties (-0.02), and terminal bonus/penalty.
    # We normalize this into a continuous 0.01 to 0.99 scale for the grader.
    total = sum(rewards)
    normalized = (total + 0.5) / 1.5
    
    # Ensure it's bounded strictly between (0, 1)
    return min(max(round(normalized, 4), 0.01), 0.99)