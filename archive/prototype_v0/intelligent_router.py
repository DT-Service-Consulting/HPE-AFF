class DeploymentRouter:
    def __init__(self, generator_model: str, critic_model: str):
        self.generator_model = generator_model
        self.critic_model = critic_model

    def choose_generator(self, field_count: int, text_length: int) -> str:
        # Simple heuristic: use stronger model for larger or more complex forms
        if field_count > 30 or text_length > 4000:
            return self.critic_model
        return self.generator_model
