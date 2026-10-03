import { Button as ButtonPrimitive } from '@base-ui/react/button';

import { cn } from '@/lib/utils';

function Button({ className, ...props }: ButtonPrimitive.Props) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(
        "inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md border border-transparent bg-gradient-to-b from-button-from to-button-to px-5 text-sm font-medium whitespace-nowrap text-white shadow-sm transition-all outline-none select-none hover:from-button-hover-from hover:to-button-hover-to hover:shadow-md focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  );
}

export { Button };
