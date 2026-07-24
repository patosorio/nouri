class AppError(Exception):
    def __init__(self, message: str, code: str = "app_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message=message, code="RESOURCE_NOT_FOUND")


class OwnershipError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message=message, code="RESOURCE_NOT_FOUND")


class TierGateError(AppError):
    def __init__(self, message: str = "This feature requires a paid plan.") -> None:
        super().__init__(message=message, code="TIER_GATE")


class PlanGenerationFailedError(AppError):
    def __init__(
        self,
        message: str = "Plan generation failed after max repair iterations",
    ) -> None:
        super().__init__(message=message, code="PLAN_GENERATION_FAILED")



class NutritionOutOfRangeError(AppError):
    def __init__(self, message: str, field: str, value: float) -> None:
        self.field = field
        self.value = value
        super().__init__(message=message, code="NUTRITION_OUT_OF_RANGE")
