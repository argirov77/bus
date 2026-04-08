import React from "react";

export default function Skeleton({ rows = 3, height = 18, gap = 10 }) {
  return (
    <div className="skeleton-wrap" aria-busy="true" aria-label="Loading...">
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="skeleton-line"
          style={{
            height,
            marginBottom: i < rows - 1 ? gap : 0,
            width: i === rows - 1 ? "60%" : "100%"
          }}
        />
      ))}
    </div>
  );
}
