import { cva, type VariantProps } from "class-variance-authority"
import type * as React from "react"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex h-5 w-fit shrink-0 items-center gap-1 rounded-[4px] border px-1.5 text-[11px] font-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        pending: "border-border bg-subtle text-pending",
        ok: "border-ok/30 bg-ok/10 text-ok",
        warn: "border-warn/30 bg-warn-bg text-warn",
        reject: "border-reject/30 bg-reject/10 text-reject",
        outline: "border-border text-muted-foreground",
      },
    },
    defaultVariants: { variant: "outline" },
  }
)

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge }
