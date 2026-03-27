from abc import ABC, abstractmethod


class BaseChannelAdapter(ABC):
    channel_code: str

    @abstractmethod
    def validate_connection(self, connection) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def push_ari(self, connection, ari_updates: list[dict]) -> dict:
        raise NotImplementedError

    @abstractmethod
    def pull_reservations(self, connection, cursor: dict | None = None) -> dict:
        raise NotImplementedError

    @abstractmethod
    def acknowledge_reservation(
        self,
        connection,
        external_reservation_id: str,
        payload: dict | None = None,
    ) -> dict:
        raise NotImplementedError