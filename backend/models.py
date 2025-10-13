from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List
from enum import Enum

# --- Модели за Stop ---
class StopBase(BaseModel):
    stop_name: str
    stop_en: Optional[str] = None
    stop_bg: Optional[str] = None
    stop_ua: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None

class StopCreate(StopBase):
    pass

class Stop(StopBase):
    id: int
    class Config:
        from_attributes = True  # за Pydantic v2

# --- Модели за Route ---
class RouteBase(BaseModel):
    name: str
    is_demo: bool = False

class RouteCreate(RouteBase):
    pass

class Route(RouteBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели за RouteStop ---
class RouteStopBase(BaseModel):
    route_id: int
    stop_id: int
    order: int
    arrival_time: Optional[datetime] = None
    departure_time: Optional[datetime] = None

class RouteStopCreate(RouteStopBase):
    pass

class RouteStop(RouteStopBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели за Pricelist ---
class PricelistBase(BaseModel):
    name: str
    currency: str = "UAH"

class PricelistCreate(PricelistBase):
    pass

class Pricelist(PricelistBase):
    id: int
    is_demo: bool = False
    class Config:
        from_attributes = True

class PricelistDemoUpdate(BaseModel):
    is_demo: bool

# --- Модели за Prices ---
class PricesBase(BaseModel):
    pricelist_id: int
    departure_stop_id: int
    arrival_stop_id: int
    price: float

class PricesCreate(PricesBase):
    pass

class Prices(PricesBase):
    id: int
    class Config:
        from_attributes = True
# --- Модели за RoutePricelistBundle ---
class RoutePricelistBundleBase(BaseModel):
    route_forward_id: int
    route_backward_id: int
    pricelist_id: int

class RoutePricelistBundleCreate(RoutePricelistBundleBase):
    pass

class RoutePricelistBundle(RoutePricelistBundleBase):
    id: int
    class Config:
        from_attributes = True


# --- Модели за Tour ---
# За вход при създаване използваме layout_variant и active_seats, а общият брой места се пресмята на бекенда
class BookingTermsEnum(int, Enum):
    """Варианты условий бронирования."""

    EXPIRE_AFTER_48H = 0  # бронь сгорает через 48 часов после оформления
    EXPIRE_BEFORE_48H = 1  # бронь сгорает за 48 часов до выезда
    NO_EXPIRY = 2          # бронь не сгорает, оплата при посадке
    NO_BOOKING = 3         # бронирование недоступно, только оплата


class TourBase(BaseModel):
    route_id: int
    pricelist_id: int
    date: date
    layout_variant: int  # избран вариант на разположение (напр. 1 – Neoplan, 2 – Travego)
    booking_terms: BookingTermsEnum = BookingTermsEnum.EXPIRE_AFTER_48H

class TourCreate(TourBase):
    active_seats: List[int]  # номера на активните места за продажба

# При извеждане се връща и изчисленият общ брой места (seats)
class Tour(TourBase):
    id: int
    seats: int
    class Config:
        from_attributes = True

# --- Модели за Passenger ---
class PassengerBase(BaseModel):
    name: str

class PassengerCreate(PassengerBase):
    pass

class Passenger(PassengerBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели за Ticket ---
class TicketBase(BaseModel):
    tour_id: int
    seat_id: int
    passenger_id: int
    departure_stop_id: int
    arrival_stop_id: int
    purchase_id: Optional[int] = None
    extra_baggage: int = 0

class TicketCreate(TicketBase):
    pass

class Ticket(TicketBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели за Available ---
class AvailableBase(BaseModel):
    tour_id: int
    departure_stop_id: int
    arrival_stop_id: int
    seats: int

class AvailableCreate(AvailableBase):
    pass

class Available(AvailableBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели за Seat ---
class SeatBase(BaseModel):
    tour_id: int
    seat_num: int
    available: str  # Низ, съдържащ свободните сегменти, напр. "1234" или "0" ако мястото е деактивирано

class SeatCreate(SeatBase):
    pass

class Seat(SeatBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели за User ---
class UserBase(BaseModel):
    username: str
    email: str
    role: str

class UserCreate(UserBase):
    hashed_password: str

class User(UserBase):
    id: int
    hashed_password: str
    class Config:
        from_attributes = True

# --- Модели за Purchase и Sales ---

class PurchaseBase(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    amount_due: Optional[float] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None
    update_at: Optional[datetime] = None
    payment_method: Optional[str] = None

class PurchaseCreate(PurchaseBase):
    pass

class Purchase(PurchaseBase):
    id: int
    class Config:
        from_attributes = True


class PurchaseLog(BaseModel):
    id: int
    at: datetime
    action: str
    amount: float
    purchase_id: Optional[int] = None
    by: Optional[str] = None
    method: Optional[str] = None

    class Config:
        from_attributes = True

# --- Дополнительные модели для bundle ---
class LangRequest(BaseModel):
    lang: str

class LocalizedStop(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    arrival_time: Optional[str] = None
    departure_time: Optional[str] = None

class LocalizedRoute(BaseModel):
    id: int
    name: str
    stops: List[LocalizedStop]

class RoutesBundleOut(BaseModel):
    forward: LocalizedRoute
    backward: LocalizedRoute

class PriceLocalized(BaseModel):
    departure_stop_id: int
    departure_name: str
    arrival_stop_id: int
    arrival_name: str
    price: float

class PricelistBundleOut(BaseModel):
    pricelist_id: int
    currency: str
    prices: List[PriceLocalized]

# --- New models for selected routes/pricelist endpoints ---

class IdItem(BaseModel):
    id: int

class PricelistItem(IdItem):
    currency: str

class AdminSelectedRoutesOut(BaseModel):
    routes: List[IdItem]

class AdminSelectedPricelistOut(BaseModel):
    pricelist: PricelistItem

class AdminSelectedRoutesIn(BaseModel):
    routes: List[int]

class AdminSelectedPricelistIn(BaseModel):
    pricelist_id: int

class SuccessResponse(BaseModel):
    success: bool
