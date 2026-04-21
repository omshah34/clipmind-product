// Catches any stray /login redirects and sends them to the real signin page
import { redirect } from "next/navigation";

export default function LoginPage() {
  redirect("/auth/signin");
}
