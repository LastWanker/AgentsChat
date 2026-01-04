from events.types import Decision

class IntentConstraintPolicy:
    def __init__(self, interpreter):
        self.interpreter = interpreter

    def apply(self, intention, agent, world, store) -> Decision:
        return self.interpreter.interpret_intention(intention, agent, world, store)
