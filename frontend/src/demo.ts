// Demo-mode notice. On by default; a real deployment would build with VITE_DEMO_NOTICE=0.
export const SHOW_DEMO_NOTICE = import.meta.env.VITE_DEMO_NOTICE !== "0";
export const DEMO_NOTICE_BOTH =
  "This is a demo. Please don't enter real personal information. · Esto es una demostración. Por favor no escriba información personal real.";
