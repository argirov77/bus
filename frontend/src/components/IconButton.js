// src/components/IconButton.js
import React from 'react';

const IconButton = ({ icon, alt, onClick, type = "button", className = "" }) => (
  <button type={type} className={`btn btn--sm ${className}`.trim()} onClick={onClick}>
    <img src={icon} alt={alt} />
  </button>
);

export default IconButton;
