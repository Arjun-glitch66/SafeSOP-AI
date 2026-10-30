import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App.jsx";
// Self-hosted fonts (OFL), bundled by Vite: no request to a third-party font service.
import "@fontsource-variable/archivo/wdth.css";
import "@fontsource-variable/public-sans/index.css";
import "@fontsource-variable/source-serif-4/opsz.css";
import { AuthProvider, BackendProvider, NoticeProvider } from "./state.jsx";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <BackendProvider>
        <NoticeProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </NoticeProvider>
      </BackendProvider>
    </BrowserRouter>
  </StrictMode>
);
