import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-pill border border-transparent bg-clip-padding font-sans text-btn font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-cta text-white hover:bg-[#db4750]",
        outline:
          "border-[1.5px] border-primary bg-transparent text-primary hover:bg-primary/10 aria-expanded:bg-primary/10",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-primary/20",
        ghost:
          "text-text hover:bg-primary/8 aria-expanded:bg-primary/8",
        destructive:
          "bg-cta/15 text-cta hover:bg-cta/25 focus-visible:border-cta/40 focus-visible:ring-cta/20",
        link: "rounded-none text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 gap-2 px-5 has-data-[icon=inline-end]:pr-4 has-data-[icon=inline-start]:pl-4",
        xs: "h-7 gap-1 px-2.5 font-mono text-label uppercase tracking-wide [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 px-3.5 text-body-sm has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-2 px-5 text-btn",
        icon: "size-8 rounded-card",
        "icon-xs": "size-6 rounded-card [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-card",
        "icon-lg": "size-9 rounded-card",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
