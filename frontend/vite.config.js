import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const port = parseInt(env.VITE_PORT || process.env.PORT || "5174", 10);
  return {
    plugins: [react()],
    server: {
      port: port,
      strictPort: false,
    },
  };
});
