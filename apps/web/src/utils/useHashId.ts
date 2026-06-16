import { useEffect, useState } from "react";
import { currentHashId } from "./navigation";

export function useHashId() {
  const [id, setId] = useState(() => currentHashId());

  useEffect(() => {
    const sync = () => setId(currentHashId());
    window.addEventListener("hashchange", sync);
    sync();
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  return id;
}
