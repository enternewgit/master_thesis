"use client";
import dynamic from "next/dynamic";
import EEGRunner from "./components/EEG/EEGRunner";

const Chart = dynamic(() => import("./components/Chart/chart"), { ssr: false });

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex h-14 items-center px-4 bg-indigo-800 text-white">
        <span className="text-lg font-bold">EEG → Music Lab</span>
        <div className="ml-auto">
          <EEGRunner />
        </div>
      </header>
      <main className="p-4">
        <Chart />
      </main>
    </div>
  );
}
