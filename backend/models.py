from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List

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

class PricelistCreate(PricelistBase):
    pass

class Pricelist(PricelistBase):
    id: int
    class Config:
        from_attributes = True

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

# --- Модели за Tour ---
# За вход при създаване използваме layout_variant и active_seats, а общият брой места се пресмята на бекенда
class TourBase(BaseModel):
    route_id: int
    pricelist_id: int
    date: date
    layout_variant: int  # избран вариант на разположение (напр. 1 – Neoplan, 2 – Travego)
    booking_terms: str | None = None

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


class Sales(BaseModel):
    id: int
    date: datetime
    category: str
    amount: float
    purchase_id: Optional[int] = None
    comment: Optional[str] = None
    class Config:
        from_attributes = True
