import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { BrowserRouter } from "react-router-dom";
import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import "@mantine/core/styles.css";

import App from "./App";
import { AuthProvider } from "./lib/auth";
import "./index.css";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <AuthProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AuthProvider>
      </MantineProvider>
    </QueryClientProvider>
  </StrictMode>,
);
