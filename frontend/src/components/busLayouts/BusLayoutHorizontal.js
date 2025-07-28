import React from "react";
import doorIcon from "../../assets/icons/door.svg";
import wheelIcon from "../../assets/icons/wheel.svg";

// build two horizontal rows, door at [0] of top row, wheel at [0] of bottom row, wc at end of top row
const topRow = ["door", ...Array.from({length:24}, (_,i)=>i+1), "wc"];
const bottomRow = ["wheel", ...Array.from({length:25}, (_,i)=>i+25)];
const layout = [topRow, bottomRow];

export default function BusLayoutHorizontal({ renderCell }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {layout.map((row,rowIdx)=>(
        <div key={rowIdx} style={{ display:"flex", gap:4 }}>
          {row.map((cell,cellIdx)=>{
            if (cell === "door") {
              return <img key={cellIdx} src={doorIcon} alt="Door" style={{width:40,height:40}} />;
            }
            if (cell === "wheel") {
              return <img key={cellIdx} src={wheelIcon} alt="Steering wheel" style={{width:40,height:40}} />;
            }
            if (cell === "wc") {
              return (
                <div key={cellIdx} style={{width:40,height:40,display:"flex",alignItems:"center",justifyContent:"center",border:"1px solid #888",borderRadius:4}}>
                  WC
                </div>
              );
            }
            return (
              <React.Fragment key={cellIdx}>
                {typeof renderCell === "function" ? renderCell(cell) : cell}
              </React.Fragment>
            );
          })}
        </div>
      ))}
    </div>
  );
}
