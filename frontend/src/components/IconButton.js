// src/components/IconButton.js
import React from 'react';

const IconButton = ({ icon, alt, onClick }) => (
  <button className="icon-btn" onClick={onClick}>
    <img src={icon} alt={alt} />
  </button>
);

export default IconButton;
