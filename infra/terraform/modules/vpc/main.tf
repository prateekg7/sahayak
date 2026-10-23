resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "sahayak-${var.environment}-vpc"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "sahayak-${var.environment}-igw"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# Public subnets (ALB, NAT Gateways)
resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name        = "sahayak-${var.environment}-public-${var.availability_zones[count.index]}"
    Environment = var.environment
    Service     = "sahayak"
    Type        = "public"
    ManagedBy   = "terraform"
  }
}

# Elastic IP for NAT Gateway
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name        = "sahayak-${var.environment}-nat-eip"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

# NAT Gateway (in first public subnet)
resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name        = "sahayak-${var.environment}-nat"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }

  depends_on = [aws_internet_gateway.gw]
}

# Private application subnets (ECS tasks)
resource "aws_subnet" "private_app" {
  count             = length(var.private_app_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_app_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name        = "sahayak-${var.environment}-private-app-${var.availability_zones[count.index]}"
    Environment = var.environment
    Service     = "sahayak"
    Type        = "private-app"
    ManagedBy   = "terraform"
  }
}

# Private database subnets (RDS PostgreSQL, ElastiCache Redis)
resource "aws_subnet" "private_db" {
  count             = length(var.private_db_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_db_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name        = "sahayak-${var.environment}-private-db-${var.availability_zones[count.index]}"
    Environment = var.environment
    Service     = "sahayak"
    Type        = "private-db"
    ManagedBy   = "terraform"
  }
}

# Route table for public subnets -> Internet Gateway
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = {
    Name        = "sahayak-${var.environment}-public-rt"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Route table for private app subnets -> NAT Gateway
resource "aws_route_table" "private_app" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }

  tags = {
    Name        = "sahayak-${var.environment}-private-app-rt"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_route_table_association" "private_app" {
  count          = length(aws_subnet.private_app)
  subnet_id      = aws_subnet.private_app[count.index].id
  route_table_id = aws_route_table.private_app.id
}

# Route table for isolated private DB subnets (no internet route)
resource "aws_route_table" "private_db" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "sahayak-${var.environment}-private-db-rt"
    Environment = var.environment
    Service     = "sahayak"
    ManagedBy   = "terraform"
  }
}

resource "aws_route_table_association" "private_db" {
  count          = length(aws_subnet.private_db)
  subnet_id      = aws_subnet.private_db[count.index].id
  route_table_id = aws_route_table.private_db.id
}
