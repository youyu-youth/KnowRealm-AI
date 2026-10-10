import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { createQueryClient } from "@/app/queryClient";
import { LoadingState } from "@/components/common/LoadingState";
import { appToast } from "@/components/common/appToastManager";
import { prepareAppearance } from "@/features/settings/appearanceCache";
import i18n from "@/i18n";
import "./styles/globals.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Application root is missing");
const root = ReactDOM.createRoot(rootElement);
const queryClient = createQueryClient();
root.render(<LoadingState />);
void prepareAppearance(queryClient).then((error) => {
  root.render(
    <React.StrictMode>
      <App queryClient={queryClient} />
    </React.StrictMode>,
  );
  if (error)
    appToast.add({
      type: "error",
      description: i18n.t("settings.preferences.startupFailed"),
    });
});
