import eslint from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    rules: {
      // Сурагчдын "ашиглаагүй хувьсагч"-ийг барьж авах гол дүрэм
      "@typescript-eslint/no-unused-vars": "error",
    },
  },
);
