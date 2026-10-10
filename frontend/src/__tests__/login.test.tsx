import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/pages/LoginPage";
import { AuthProvider } from "@/lib/auth";
import { setApiKey } from "@/lib/api";

function renderLogin() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <LoginPage />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("LoginPage", () => {
  afterEach(() => {
    setApiKey(null);
    vi.unstubAllGlobals();
  });

  it("requires a key before submitting", async () => {
    renderLogin();
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Enter your GitPulse API key/);
  });

  it("shows a clear message for an unrecognised key and keeps no session", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "invalid API key" }), { status: 401 })));
    renderLogin();
    await userEvent.type(screen.getByLabelText(/api key/i), "wrong-key");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/not recognised/));
    expect(sessionStorage.getItem("gitpulse.apiKey")).toBeNull();
  });
});
