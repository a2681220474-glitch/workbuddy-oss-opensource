import { Table } from "antd";
import type { TableProps } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { HTMLAttributes, MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { useMemo, useRef, useState } from "react";

interface ResizableHeaderCellProps extends HTMLAttributes<HTMLTableCellElement> {
  width?: number;
  onResizeColumn?: (width: number) => void;
  children?: ReactNode;
}

function ResizableHeaderCell({ width, onResizeColumn, children, ...restProps }: ResizableHeaderCellProps) {
  const cellRef = useRef<HTMLTableCellElement>(null);

  const startResize = (event: ReactMouseEvent<HTMLSpanElement>) => {
    if (!onResizeColumn) return;
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startWidth = cellRef.current?.offsetWidth ?? width ?? 120;

    const onMove = (moveEvent: MouseEvent) => {
      const nextWidth = Math.max(80, startWidth + moveEvent.clientX - startX);
      onResizeColumn(nextWidth);
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  return (
    <th ref={cellRef} {...restProps}>
      <span className="resizable-cell-content">{children}</span>
      {width ? <span className="column-resize-handle" onMouseDown={startResize} /> : null}
    </th>
  );
}

export function ResizableTable<T extends object>({ columns, className, ...props }: TableProps<T>) {
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});

  const mergedColumns = useMemo(() => {
    return (columns ?? []).map((column, index) => {
      const typedColumn = column as Record<string, unknown>;
      const dataIndex = typedColumn.dataIndex;
      const columnKey = String(column.key ?? (Array.isArray(dataIndex) ? dataIndex.join(".") : dataIndex) ?? index);
      const storedWidth = columnWidths[columnKey];
      const currentWidth = storedWidth ?? (Number(column.width ?? 0) || undefined);
      const existingHeaderCell = column.onHeaderCell;
      return {
        ...column,
        width: currentWidth ?? column.width,
        onHeaderCell: (col: unknown) => ({
          ...(existingHeaderCell ? existingHeaderCell(col as never) : {}),
          width: currentWidth,
          onResizeColumn: (nextWidth: number) => setColumnWidths((current) => ({ ...current, [columnKey]: nextWidth }))
        })
      };
    }) as ColumnsType<T>;
  }, [columnWidths, columns]);

  return (
    <Table<T>
      {...props}
      className={["resizable-table", className].filter(Boolean).join(" ")}
      columns={mergedColumns}
      components={{ header: { cell: ResizableHeaderCell } }}
    />
  );
}
