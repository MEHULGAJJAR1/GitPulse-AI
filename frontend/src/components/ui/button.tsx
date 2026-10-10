import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

// shadcn-style primitive (class-variance-authority + tailwind-merge), styled for the dark glass theme.
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-all duration-200 disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none cursor-pointer active:scale-[0.98]",
  {
    variants: {
      variant: {
        default: "bg-gradient-to-r from-cyan-400 to-violet-500 text-ink-950 font-semibold shadow-lg shadow-cyan-500/20 hover:brightness-110",
        secondary: "glass text-slate-100 hover:bg-white/10",
        ghost: "text-slate-300 hover:bg-white/5 hover:text-white",
        danger: "bg-rose-500/15 text-rose-200 border border-rose-400/30 hover:bg-rose-500/25",
        outline: "border border-slate-600/60 text-slate-200 hover:bg-white/5",
      },
      size: { sm: "h-8 px-3 text-xs", md: "h-10 px-4", lg: "h-11 px-6 text-base", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => (
  <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
));
Button.displayName = "Button";
