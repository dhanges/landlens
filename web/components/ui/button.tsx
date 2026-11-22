import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

// web/DESIGN.md: one filled sage (primary) button per view; everything else outlined or a walnut link.
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium no-underline transition-colors disabled:pointer-events-none disabled:opacity-55 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-on-primary hover:bg-primary/90 hover:text-on-primary",
        outline: "border border-border bg-surface text-text hover:bg-bg hover:text-text",
        link: "h-auto px-0 py-0 font-normal text-accent hover:text-accent-hover",
        ghost: "text-text hover:bg-bg hover:text-text",
      },
      size: {
        default: "h-10 px-4 text-[15px]",
        lg: "px-[22px] py-[14px] text-base",
        sm: "h-8 px-3 text-[14px]",
        block: "h-11 w-full px-4 text-[15px]",
      },
    },
    defaultVariants: { variant: "outline", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size }), className)} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { buttonVariants };
