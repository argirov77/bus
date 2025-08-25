import React, { useState } from 'react';
import passIcon from '../assets/icons/pass.svg';

// Displays a banner with passenger count. On click toggles controls
// to adjust adult and discount passenger numbers.
export default function PassengerSelector({
  adultCount,
  discountCount,
  onAdultChange,
  onDiscountChange
}) {
  const [open, setOpen] = useState(false);
  const total = adultCount + discountCount;

  const adjustAdult = delta => {
    const next = Math.max(0, adultCount + delta);
    onAdultChange(next);
  };

  const adjustDiscount = delta => {
    const next = Math.max(0, discountCount + delta);
    onDiscountChange(next);
  };

  return (
    <div style={{ position: 'relative' }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          border: '1px solid #ccc',
          padding: '4px 8px',
          borderRadius: 4,
          cursor: 'pointer'
        }}
      >
        <img src={passIcon} alt="passengers" style={{ width: 16, height: 16, marginRight: 4 }} />
        <span>{total}</span>
      </div>
      {open && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            background: '#fff',
            border: '1px solid #ccc',
            padding: 8,
            marginTop: 4,
            zIndex: 100,
            borderRadius: 4
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
            <span style={{ flexGrow: 1 }}>Взрослые</span>
            <button type="button" onClick={() => adjustAdult(-1)}>-</button>
            <span style={{ margin: '0 8px' }}>{adultCount}</span>
            <button type="button" onClick={() => adjustAdult(1)}>+</button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <span style={{ flexGrow: 1 }}>Льготные</span>
            <button type="button" onClick={() => adjustDiscount(-1)}>-</button>
            <span style={{ margin: '0 8px' }}>{discountCount}</span>
            <button type="button" onClick={() => adjustDiscount(1)}>+</button>
          </div>
        </div>
      )}
    </div>
  );
}
