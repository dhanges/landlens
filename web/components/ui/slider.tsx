"use client";

import * as SliderPrimitive from "@radix-ui/react-slider";
import * as React from "react";

import { cn } from "@/lib/utils";

/** 4px track in --border, sage range, 18px surface thumb with a 2px sage ring (Map mockup). */
export const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root
    ref={ref}
    className={cn("relative flex h-[18px] w-full touch-none select-none items-center", className)}
    {...props}
  >
    <SliderPrimitive.Track className="relative h-1 w-full grow overflow-hidden rounded-sm bg-border">
      <SliderPrimitive.Range className="absolute h-full rounded-sm bg-primary" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb
      aria-label={props["aria-label"]}
      className="block h-[18px] w-[18px] rounded-full border-2 border-primary bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    />
  </SliderPrimitive.Root>
));
Slider.displayName = "Slider";
