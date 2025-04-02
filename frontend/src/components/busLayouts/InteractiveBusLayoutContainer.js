import React from "react";
import BusLayoutNeoplan from "./BusLayoutNeoplan";
import BusLayoutTravego from "./BusLayoutTravego";

const InteractiveBusLayoutContainer = ({ layoutVariant, selectedSeats, toggleSeat }) => {
  if (layoutVariant === "1" || layoutVariant === 1) {
    return (
      <BusLayoutNeoplan 
        selectedSeats={selectedSeats} 
        toggleSeat={toggleSeat} 
      />
    );
  } else if (layoutVariant === "2" || layoutVariant === 2) {
    return (
      <BusLayoutTravego 
        selectedSeats={selectedSeats} 
        toggleSeat={toggleSeat} 
      />
    );
  } else {
    return null;
  }
};

export default InteractiveBusLayoutContainer;
