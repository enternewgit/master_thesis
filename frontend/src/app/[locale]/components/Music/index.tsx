"use client";
import dynamic from "next/dynamic";

const Player = dynamic(() => import("./Player"), { ssr: false });

export default function MusicComponent() {
  return (
    <div>
      <p>音楽生成のプリセットを選んで、脳波に合わせた生成や分析を行えます。</p>
      <div style={{ border: "1px solid #eee", padding: 12, borderRadius: 6 }}>
        <Player />
      </div>
    </div>
  );
}
