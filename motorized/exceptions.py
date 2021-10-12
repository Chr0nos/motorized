class MotorizedError(Exception):
    pass


class NotConnectedException(MotorizedError):
    pass


class DocumentNotSavedError(MotorizedError):
    pass
