// Mirrors app/schemas/*.py exactly. Decimal fields serialize as JSON strings (Pydantic v2
// default, confirmed against the live API), never numbers — always format, never assume float.

export type AccountStatus = "ACTIVE" | "DEACTIVATED";
export type ProductStatus = "ACTIVE" | "DISCONTINUED";
export type CategoryStatus = "ACTIVE" | "INACTIVE";
export type OrderStatus = "CONFIRMED" | "CANCELLED";
export type ProductSortField = "price" | "newest" | "popularity" | "rating";
export type SortOrder = "asc" | "desc";

// --- auth ---

export interface RegisterRequest {
  email: string;
  password: string;
  city?: string | null;
  state?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface UserOut {
  user_id: string;
  email: string;
  registration_date: string;
  account_status: AccountStatus;
  city: string | null;
  state: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserOut;
}

// --- users / addresses ---

export interface UserUpdateRequest {
  city?: string | null;
  state?: string | null;
}

export interface AddressOut {
  address_id: string;
  address_line1: string;
  address_line2: string | null;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_default: boolean;
}

export interface AddressCreateRequest {
  address_line1: string;
  address_line2?: string | null;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_default?: boolean;
}

export type AddressUpdateRequest = Partial<AddressCreateRequest>;

// --- catalog ---

export interface CategoryOut {
  category_id: string;
  category_name: string;
  category_status: CategoryStatus;
}

export interface ProductOut {
  product_id: string;
  product_name: string;
  category_id: string;
  brand: string | null;
  base_price: string;
  product_status: ProductStatus;
  description: string | null;
  image_url: string | null;
  average_rating: number | null;
  review_count: number;
}

export interface ProductListResponse {
  items: ProductOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProductListParams {
  q?: string;
  category_id?: string;
  brand?: string;
  min_price?: string;
  max_price?: string;
  min_rating?: number;
  max_rating?: number;
  availability?: boolean;
  sort?: ProductSortField;
  order?: SortOrder;
  page?: number;
  page_size?: number;
}

// --- reviews ---

export interface ReviewOut {
  review_id: string;
  reviewer_name: string;
  rating: number;
  review_text: string | null;
  created_at: string;
  is_own: boolean;
}

export interface ReviewListResponse {
  items: ReviewOut[];
  total: number;
  average_rating: number | null;
}

export interface ReviewCreateRequest {
  reviewer_name: string;
  rating: number;
  review_text?: string | null;
}

// --- cart ---

export interface CartItemOut {
  cart_item_id: string;
  product_id: string;
  product_name: string;
  product_status: ProductStatus;
  quantity: number;
  unit_price: string;
  line_subtotal: string;
}

export interface CartOut {
  cart_id: string | null;
  items: CartItemOut[];
  item_count: number;
  total_quantity: number;
}

export interface CartAddItemRequest {
  product_id: string;
  quantity: number;
}

export interface CartUpdateItemRequest {
  quantity: number;
}

// --- wishlist ---

export interface WishlistItemOut {
  wishlist_item_id: string;
  product_id: string;
  product_name: string;
  product_status: ProductStatus;
  base_price: string;
}

export interface WishlistOut {
  wishlist_id: string;
  items: WishlistItemOut[];
}

// --- checkout ---

export interface BuyNowLine {
  product_id: string;
  quantity: number;
}

export interface CheckoutStartRequest {
  buy_now?: BuyNowLine | null;
}

export interface CheckoutSnapshotOut {
  checkout_id: string;
  cart_id: string | null; // null for a buy-now snapshot — no cart is involved (§32)
  item_count: number;
  total_quantity: number;
  gross_merchandise_value: string;
  discount_amount: string;
  cart_net_value: string;
  currency: string;
}

// --- orders ---

export interface OrderCreateRequest {
  checkout_id: string;
  address_id: string;
  buy_now?: BuyNowLine | null;
}

export interface OrderItemOut {
  order_item_id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: string;
  discount_amount: string;
  line_revenue: string;
  currency: string;
}

export interface OrderOut {
  order_id: string;
  checkout_id: string;
  status: OrderStatus;
  total_amount: string;
  currency: string;
  item_count: number;
  total_quantity: number;
  shipping_address_line1: string;
  shipping_address_line2: string | null;
  shipping_city: string;
  shipping_state: string;
  shipping_postal_code: string;
  shipping_country: string;
  created_at: string;
  confirmed_at: string;
  cancelled_at: string | null;
  items: OrderItemOut[];
}

export interface OrderSummaryOut {
  order_id: string;
  status: OrderStatus;
  total_amount: string;
  currency: string;
  item_count: number;
  total_quantity: number;
  created_at: string;
  cancelled_at: string | null;
}

export interface OrderListResponse {
  items: OrderSummaryOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiErrorBody {
  detail: string | { msg: string; loc: (string | number)[] }[];
}
