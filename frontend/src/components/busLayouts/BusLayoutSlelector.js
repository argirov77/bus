import React from "react";
import BusLayoutNeoplan from "./BusLayoutNeoplan";
import BusLayoutTravego from "./BusLayoutTravego";
import BusLayoutHorizontal from "./BusLayoutHorizontal";

const BusLayoutSelector = ({ layout_variant, seats, onSelect, interactive }) => {
  if (layout_variant === 1) {
    return <BusLayoutNeoplan seats={seats} onSelect={onSelect} interactive={interactive} />;
  }
  if (layout_variant === 2) {
    return <BusLayoutTravego seats={seats} onSelect={onSelect} interactive={interactive} />;
  }
  if (layout_variant === 3) {
    return <BusLayoutHorizontal seats={seats} onSelect={onSelect} interactive={interactive} />;
  }
  return <div>Layout не выбран</div>;
};

export default BusLayoutSelector;
