// src/components/IconButton.js
import React from 'react';

const IconButton = ({ icon, alt, onClick, type = "button", className = "", disabled = false }) => (
  <button
    type={type}
    className={`btn btn--sm ${className}`.trim()}
    onClick={onClick}
    disabled={disabled}
  >
    <img src={icon} alt={alt} />
  </button>
);

export default IconButton;
